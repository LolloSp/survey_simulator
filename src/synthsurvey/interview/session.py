"""Un'intervista: una persona, una modalità, una replica, un modello.

Qui stanno le strutture comuni ai tre driver (CAWI in `cawi.py`, CATI e
CAPI in `dialogue.py`): specifica dell'intervista, generatore casuale
derivato dal seed di progetto, risultato con record, risposte per il routing,
trascrizione e contatori.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from synthsurvey.config.schema import SynthSurveyConfig
from synthsurvey.interview.records import (
    AnswerRecord,
    AnswerStatus,
    AnswerValue,
    InterviewOutcome,
)
from synthsurvey.llm.pool import LLMPool
from synthsurvey.personas.schema import Persona
from synthsurvey.questionnaire.modes import Mode, ModeQuestionnaire
from synthsurvey.questionnaire.schema import Question, Questionnaire

MODE_INDEX = {Mode.CAWI: 0, Mode.CATI: 1, Mode.CAPI: 2}


@dataclass(frozen=True)
class InterviewSpec:
    run_id: str
    persona: Persona
    persona_index: int  # posizione nel campione, per il seed
    mode: Mode
    replicate: int  # da 1
    model: str
    seed: int


@dataclass
class Turn:
    """Una battuta della trascrizione (CATI e CAPI; in CAWI una pagina per turno)."""

    speaker: str  # intervistatore | rispondente | sistema
    text: str
    question_id: str | None = None
    signals: dict[str, Any] | None = None


@dataclass
class InterviewResult:
    spec: InterviewSpec
    records: list[AnswerRecord] = field(default_factory=list)
    answers: dict[str, AnswerValue] = field(default_factory=dict)  # valori per il routing
    outcome: InterviewOutcome = field(default_factory=lambda: InterviewOutcome(completed=False))
    transcript: list[Turn] = field(default_factory=list)

    @property
    def persona_id(self) -> str:
        return self.spec.persona.persona_id


def interview_rng(spec: InterviewSpec) -> np.random.Generator:
    """Generatore dedicato all'intervista: seed di progetto, persona, modalità, replica.

    Il ramo 7 è riservato alle interviste (4 alle persone, gli altri al campione).
    """
    seq = np.random.SeedSequence(
        [spec.seed, 7, spec.persona_index, MODE_INDEX[spec.mode], spec.replicate]
    )
    return np.random.default_rng(seq)


def variant_for(spec: InterviewSpec, step: str) -> str:
    """Chiave di variante per la cache: stessa intervista e stesso passo, stessa risposta."""
    return f"{spec.seed}:{spec.persona.persona_id}:{spec.mode.value}:r{spec.replicate}:{step}"


def new_record(
    spec: InterviewSpec,
    q: Question,
    item_id: str | None,
    status: AnswerStatus,
    position: int,
    **kw: Any,
) -> AnswerRecord:
    return AnswerRecord(
        run_id=spec.run_id,
        persona_id=spec.persona.persona_id,
        segment=spec.persona.segment,
        mode=spec.mode.value,
        replicate=spec.replicate,
        model=spec.model,
        question_id=q.id,
        item_id=item_id,
        status=status,
        position=position,
        **kw,
    )


def fill_missing(
    result: InterviewResult, questionnaire: Questionnaire, status: AnswerStatus
) -> None:
    """Record per le domande mai presentate (saltate dal routing o dopo un abbandono)."""
    presenti = {(r.question_id, r.item_id) for r in result.records}
    position = max((r.position for r in result.records), default=0)
    for q in questionnaire.questions:
        chiavi = [(q.id, i.id) for i in q.items] if q.items else [(q.id, None)]
        for qid, iid in chiavi:
            if (qid, iid) in presenti:
                continue
            position += 1
            result.records.append(new_record(result.spec, q, iid, status, position))


def split_tokens(
    n_records: int, tokens_in: int, tokens_out: int, latency: int
) -> list[tuple[int, int, int]]:
    """Ripartisce i token di una chiamata fra i record che ne derivano (resto al primo)."""
    if n_records <= 0:
        return []
    base = [(tokens_in // n_records, tokens_out // n_records, latency // n_records)] * n_records
    first = (
        base[0][0] + tokens_in % n_records,
        base[0][1] + tokens_out % n_records,
        base[0][2] + latency % n_records,
    )
    return [first, *base[1:]]


async def run_interview(
    spec: InterviewSpec,
    questionnaire: Questionnaire,
    mode_questionnaire: ModeQuestionnaire,
    pool: LLMPool,
    config: SynthSurveyConfig,
) -> InterviewResult:
    """Esegue l'intervista con il driver della modalità."""
    if spec.mode is Mode.CAWI:
        from synthsurvey.interview.cawi import run_cawi

        return await run_cawi(spec, questionnaire, mode_questionnaire, pool, config)
    from synthsurvey.interview.dialogue import run_dialogue

    return await run_dialogue(spec, questionnaire, mode_questionnaire, pool, config)
