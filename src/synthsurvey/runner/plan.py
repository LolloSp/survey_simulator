"""Piano del run: quali interviste eseguire e quanto costeranno.

Disegno within-subject: ogni persona in tutte le modalità abilitate.
Between-subject: ogni persona in una sola modalità, assegnata a caso secondo
`modes.allocation` con il metodo dei resti più grandi e un generatore
derivato dal seed (ramo 9). Repliche e modelli moltiplicano il piano.
"""

from dataclasses import dataclass

import numpy as np

from synthsurvey.config.schema import Design, ModelSpec, SynthSurveyConfig
from synthsurvey.llm.pricing import Pricing
from synthsurvey.personas.schema import Persona
from synthsurvey.population.quotas import largest_remainder
from synthsurvey.questionnaire.modes import Mode, ModeQuestionnaire


@dataclass(frozen=True)
class InterviewPlan:
    persona_index: int
    persona_id: str
    mode: Mode
    replicate: int
    model_index: int

    @property
    def key(self) -> str:
        return f"{self.persona_id}:{self.mode.value}:r{self.replicate}:m{self.model_index}"


class BudgetError(Exception):
    """La stima o la spesa superano `run.budget_max_eur`."""


def assign_modes(config: SynthSurveyConfig, n: int) -> list[Mode]:
    """Una modalità per persona (between-subject), riproducibile dal seed."""
    abilitate = [Mode(m.value) for m in config.modes.enabled]
    if config.modes.design is Design.WITHIN_SUBJECT or len(abilitate) == 1:
        raise ValueError("assign_modes serve solo al disegno between-subject")
    allocation = {k.value: float(v) for k, v in (config.modes.allocation or {}).items()}
    conteggi = largest_remainder({m.value: allocation[m.value] for m in abilitate}, n)
    sequenza: list[Mode] = []
    for m in abilitate:
        sequenza.extend([m] * int(conteggi[m.value]))
    rng = np.random.default_rng(np.random.SeedSequence([config.project.seed, 9]))
    perm = rng.permutation(len(sequenza))
    return [sequenza[i] for i in perm]


def build_plan(config: SynthSurveyConfig, personas: list[Persona]) -> list[InterviewPlan]:
    """Elenco ordinato delle interviste: persona, modalità, replica, modello."""
    n = len(personas)
    if config.modes.design is Design.BETWEEN_SUBJECT and len(config.modes.enabled) > 1:
        per_persona = [[m] for m in assign_modes(config, n)]
    else:
        per_persona = [[Mode(m.value) for m in config.modes.enabled] for _ in range(n)]
    plan: list[InterviewPlan] = []
    for mi, _spec in enumerate(config.engine.models):
        for i, p in enumerate(personas):
            for mode in per_persona[i]:
                for r in range(1, config.engine.replicates + 1):
                    plan.append(InterviewPlan(i, p.persona_id, mode, r, mi))
    return plan


# --------------------------------------------------------------------------- #
# Stima dei costi
# --------------------------------------------------------------------------- #

CHARS_PER_TOKEN = 3.5  # italiano, stima prudente
SYSTEM_OVERHEAD_CHARS = 4_500  # regole del prompt del rispondente oltre la narrativa
OUTPUT_TOKENS_CAWI_PAGE = 160
OUTPUT_TOKENS_DIALOGUE = 180
INTERVIEWER_SHARE = 0.25  # quota di domande in cui interviene l'intervistatore
INTERVIEWER_INPUT_TOKENS = 1_100
INTERVIEWER_OUTPUT_TOKENS = 80


@dataclass(frozen=True)
class CostEstimate:
    interviews: int
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cost_eur: float
    budget_eur: float
    by_model: dict[str, float]

    @property
    def within_budget(self) -> bool:
        return self.cost_eur <= self.budget_eur


def _tokens(chars: float) -> int:
    return int(chars / CHARS_PER_TOKEN) + 1


def estimate_interview_tokens(
    mq: ModeQuestionnaire, narrative_chars: float, mode: Mode
) -> tuple[int, int, int]:
    """(chiamate, token in ingresso, token in uscita) per una sola intervista."""
    system = _tokens(narrative_chars + SYSTEM_OVERHEAD_CHARS)
    if mode is Mode.CAWI:
        pagine = max(1, len(mq.pages))
        testo_pagina = _tokens(sum(len(q.text) + 120 for q in mq.questions) / pagine + 200)
        calls = pagine
        tok_in = 0
        for p in range(pagine):
            # Le pagine precedenti restano nel contesto (domanda più risposta).
            tok_in += system + testo_pagina * (p + 1) + OUTPUT_TOKENS_CAWI_PAGE * p
        return calls, tok_in, OUTPUT_TOKENS_CAWI_PAGE * pagine
    n = len(mq.questions)
    testo_domanda = _tokens(sum(len(q.text) for q in mq.questions) / max(1, n) + 150)
    tok_in = 0
    for i in range(n):
        storia = min(i, 8) * (testo_domanda + OUTPUT_TOKENS_DIALOGUE)
        tok_in += system + testo_domanda + storia
    extra = int(n * INTERVIEWER_SHARE)
    # Rilanci da copione: una chiamata certa in più al rispondente per ogni domanda con probe.
    rilanci = sum(1 for q in mq.questions if q.probe)
    calls = n + rilanci + 2 * extra
    tok_in += extra * (INTERVIEWER_INPUT_TOKENS + system + testo_domanda + OUTPUT_TOKENS_DIALOGUE)
    tok_in += rilanci * (system + 2 * testo_domanda + OUTPUT_TOKENS_DIALOGUE)
    tok_out = (n + rilanci) * OUTPUT_TOKENS_DIALOGUE + extra * (
        INTERVIEWER_OUTPUT_TOKENS + OUTPUT_TOKENS_DIALOGUE
    )
    return calls, tok_in, tok_out


def estimate_cost(
    config: SynthSurveyConfig,
    plan: list[InterviewPlan],
    personas: list[Persona],
    mode_questionnaires: dict[Mode, ModeQuestionnaire],
    pricing: Pricing,
) -> CostEstimate:
    """Stima preventiva senza cache, a prezzo pieno, per il controllo del budget."""
    narrativa = {p.persona_id: len(p.narrative) for p in personas}
    calls = tok_in = tok_out = 0
    per_modello: dict[str, float] = {}
    totale_usd = 0.0
    for item in plan:
        spec: ModelSpec = config.engine.models[item.model_index]
        c, ti, to = estimate_interview_tokens(
            mode_questionnaires[item.mode], narrativa[item.persona_id], item.mode
        )
        calls += c
        tok_in += ti
        tok_out += to
        usd = pricing.estimate_usd(spec.model, ti, to)
        per_modello[spec.model] = per_modello.get(spec.model, 0.0) + usd
        totale_usd += usd
    return CostEstimate(
        interviews=len(plan),
        calls=calls,
        input_tokens=tok_in,
        output_tokens=tok_out,
        cost_usd=totale_usd,
        cost_eur=totale_usd * config.engine.eur_per_usd,
        budget_eur=config.run.budget_max_eur,
        by_model={k: round(v, 4) for k, v in per_modello.items()},
    )
