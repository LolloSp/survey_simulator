"""Modalità CAWI: il rispondente compila una pagina alla volta, senza interlocutore.

Ogni pagina è una chiamata al modello con uno schema che elenca le domande
visibili; le risposte precedenti restano nella conversazione per la
coerenza. Le domande di una pagina che dipendono (`show_if`) da altre della
stessa pagina vengono presentate in un gruppo successivo, come farebbe un
questionario web con la logica condizionale.
"""

from typing import Any

from synthsurvey.config.schema import SynthSurveyConfig
from synthsurvey.interview.prompting import render_respondent_system
from synthsurvey.interview.records import (
    AnswerStatus,
    AnswerValue,
    code_value,
    routing_value,
    status_for,
    text_value,
)
from synthsurvey.interview.schemas import normalize_value, value_schema
from synthsurvey.interview.session import (
    InterviewResult,
    InterviewSpec,
    Turn,
    fill_missing,
    interview_rng,
    new_record,
    split_tokens,
    variant_for,
)
from synthsurvey.llm.client import LLMRequest, Message
from synthsurvey.llm.pool import LLMPool
from synthsurvey.questionnaire.modes import (
    DONT_KNOW_LABEL,
    Mode,
    ModeQuestion,
    ModeQuestionnaire,
    option_order,
)
from synthsurvey.questionnaire.routing import applies, is_shown, parse, references
from synthsurvey.questionnaire.schema import Question, Questionnaire, QuestionType


def split_groups(qids: list[str], questionnaire: Questionnaire) -> list[list[str]]:
    """Spezza una pagina dove una domanda dipende da un'altra della stessa pagina."""
    groups: list[list[str]] = []
    current: list[str] = []
    for qid in qids:
        q = questionnaire.question(qid)
        refs: set[str] = set()
        if q.show_if:
            refs = {r.partition(".")[0] for r in references(parse(q.show_if))}
        if refs & set(current):
            groups.append(current)
            current = []
        current.append(qid)
    if current:
        groups.append(current)
    return groups


def page_schema(visible: list[ModeQuestion], presented: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "answers": {
                "type": "object",
                "properties": {q.id: value_schema(q, presented[q.id]) for q in visible},
                "required": [q.id for q in visible],
                "additionalProperties": False,
            },
            "abandon": {"type": "boolean"},
            "abandon_reason": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
        "required": ["answers", "abandon", "abandon_reason"],
        "additionalProperties": False,
    }


def render_page(
    page: int, n_pages: int, visible: list[ModeQuestion], presented: dict[str, list[str]]
) -> str:
    righe = [f"Pagina {page} di {n_pages}.", ""]
    for n, q in enumerate(visible, start=1):
        righe.append(f"{n}. [{q.id}] {q.text}")
        opzioni = presented[q.id]
        if q.type == QuestionType.SINGLE:
            righe.append("   Una sola risposta:")
            righe.extend(f"   - {o}" for o in opzioni)
        elif q.type == QuestionType.MULTI:
            limite = f" (al massimo {q.max_choices})" if q.max_choices else ""
            righe.append(f"   Più risposte possibili{limite}:")
            righe.extend(f"   - {o}" for o in opzioni)
        elif q.type == QuestionType.SCALE and q.scale:
            righe.append(f"   Scegli un numero da {q.scale.min} a {q.scale.max}.")
            if q.dont_know:
                righe.append(f"   Oppure: {DONT_KNOW_LABEL}")
        elif q.type == QuestionType.NUMERIC:
            unita = f" in {q.unit}" if q.unit else ""
            righe.append(f"   Scrivi un numero{unita}.")
            if q.dont_know:
                righe.append(f"   Oppure: {DONT_KNOW_LABEL}")
        elif q.type == QuestionType.OPEN:
            righe.append("   Risposta libera (puoi anche lasciare vuoto).")
        elif q.type == QuestionType.GRID and q.items:
            righe.append("   Una risposta per ogni riga:")
            righe.extend(f"   - {iid}: {testo}" for iid, testo in q.items)
            if q.scale:
                etichette = ", ".join(f"{k} = {v}" for k, v in sorted(q.scale.labels.items()))
                righe.append(
                    f"   Scala da {q.scale.min} a {q.scale.max}"
                    + (f" ({etichette})" if etichette else "")
                )
            else:
                righe.append("   Colonne: " + "; ".join(opzioni))
            if q.dont_know:
                righe.append(f"   Oppure, per ogni riga: {DONT_KNOW_LABEL}")
        righe.append("")
    righe.append("Compila la pagina e vai avanti.")
    return "\n".join(righe)


def _add_records(
    result: InterviewResult,
    q: Question,
    mq: ModeQuestion,
    value: AnswerValue,
    presented: list[str],
    page: int,
    position: int,
    tokens: tuple[int, int, int],
    *,
    nonresponse_flag: bool = False,
) -> int:
    """Uno o più record (per item nelle griglie); restituisce la posizione aggiornata."""
    spec = result.spec
    ordine = [o for o in presented if o != DONT_KNOW_LABEL] if q.options else None
    if q.type == QuestionType.GRID and q.items:
        celle = value if isinstance(value, dict) else {}
        for i in q.items:
            v = celle.get(i.id)
            position += 1
            st = status_for(v)
            result.records.append(
                new_record(
                    spec,
                    q,
                    i.id,
                    st,
                    position,
                    answer_code=code_value(q, v, i.id),
                    answer_text=text_value(v),
                    option_order=ordine,
                    item_nonresponse=st is AnswerStatus.NONRESPONSE,
                    page=page,
                    tokens_in=tokens[0],
                    tokens_out=tokens[1],
                    latency_ms=tokens[2],
                )
            )
            tokens = (0, 0, 0)
        return position
    position += 1
    st = status_for(value, open_question=q.type == QuestionType.OPEN)
    result.records.append(
        new_record(
            spec,
            q,
            None,
            st,
            position,
            answer_code=code_value(q, value),
            answer_text=text_value(value),
            option_order=ordine,
            item_nonresponse=st is AnswerStatus.NONRESPONSE or nonresponse_flag,
            page=page,
            tokens_in=tokens[0],
            tokens_out=tokens[1],
            latency_ms=tokens[2],
        )
    )
    return position


async def run_cawi(
    spec: InterviewSpec,
    questionnaire: Questionnaire,
    mode_questionnaire: ModeQuestionnaire,
    pool: LLMPool,
    config: SynthSurveyConfig,
) -> InterviewResult:
    assert spec.mode is Mode.CAWI
    rng = interview_rng(spec)
    system = render_respondent_system(spec.persona, Mode.CAWI)
    result = InterviewResult(spec)
    outcome = result.outcome
    messages: list[Message] = []
    position = 0
    abandoned = False
    n_pages = len(mode_questionnaire.pages)
    segment = spec.persona.segment
    for page, qids in mode_questionnaire.pages.items():
        for gi, group in enumerate(split_groups(qids, questionnaire)):
            visible: list[ModeQuestion] = []
            for qid in group:
                q = questionnaire.question(qid)
                if applies(q, segment) and is_shown(q, result.answers):
                    visible.append(mode_questionnaire.question(qid))
            if not visible:
                continue
            presented = {
                q.id: option_order(q, rng, config.engine.randomize_option_order) for q in visible
            }
            testo = render_page(page, n_pages, visible, presented)
            messages.append(Message("user", testo))
            request = LLMRequest(
                system=system,
                messages=tuple(messages),
                schema=page_schema(visible, presented),
                max_tokens=config.engine.max_tokens,
                effort=config.engine.effort,
                variant=variant_for(spec, f"p{page}g{gi}"),
                metadata={
                    "persona": spec.persona.persona_id,
                    "mode": "cawi",
                    "replicate": str(spec.replicate),
                    "page": str(page),
                },
            )
            response = await pool.complete(request)
            outcome.calls += 1
            outcome.tokens_in += response.usage.input_tokens
            outcome.tokens_out += response.usage.output_tokens
            outcome.latency_ms += response.latency_ms
            result.transcript.append(Turn("sistema", testo, question_id=None))
            quote = split_tokens(
                len(visible),
                response.usage.input_tokens,
                response.usage.output_tokens,
                response.latency_ms,
            )
            if response.refused or not isinstance(response.parsed, dict):
                outcome.refusals += response.refused
                outcome.warnings.append(
                    f"pagina {page}: {'rifiuto' if response.refused else 'risposta non valida'}"
                )
                messages.pop()
                for q_mode, tk in zip(visible, quote, strict=True):
                    position = _add_records(
                        result,
                        questionnaire.question(q_mode.id),
                        q_mode,
                        None,
                        presented[q_mode.id],
                        page,
                        position,
                        tk,
                        nonresponse_flag=True,
                    )
                continue
            parsed = response.parsed
            grezze = parsed.get("answers")
            risposte: dict[str, Any] = grezze if isinstance(grezze, dict) else {}
            for q_mode, tk in zip(visible, quote, strict=True):
                q = questionnaire.question(q_mode.id)
                value = normalize_value(q_mode, risposte.get(q_mode.id), presented[q_mode.id])
                position = _add_records(
                    result, q, q_mode, value, presented[q_mode.id], page, position, tk
                )
                if value is not None:
                    result.answers[q.id] = routing_value(value)
            result.transcript.append(Turn("rispondente", response.text, question_id=None))
            messages.append(Message("assistant", response.text))
            if parsed.get("abandon") is True:
                abandoned = True
                reason = parsed.get("abandon_reason")
                outcome.abandon_reason = reason if isinstance(reason, str) else None
                break
        if abandoned:
            break
    if abandoned:
        visti = {r.question_id for r in result.records}
        restanti = [q.id for q in questionnaire.questions if q.id not in visti]
        outcome.abandoned_at = restanti[0] if restanti else None
    fill_missing(
        result,
        questionnaire,
        AnswerStatus.ABANDONED if abandoned else AnswerStatus.NOT_APPLICABLE,
    )
    outcome.completed = not abandoned
    return result
