"""Record di risposta (una riga per domanda e item) e valori usati dal routing.

Due rappresentazioni convivono:

- il *valore* della risposta, nel formato che `questionnaire.routing` sa
  valutare: etichetta per le singole, lista di etichette per le multiple,
  numero per scale e numeriche, testo per le aperte, dizionario per item
  nelle griglie, `DONT_KNOW_CODE` per "non so";
- il *record* del dataset lungo (docs/SPEC.md, "Risposta"), con codice
  numerico stabile rispetto all'ordine canonico delle opzioni, testo,
  ordine presentato e paradati.
"""

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from synthsurvey.questionnaire.modes import DONT_KNOW_LABEL, Mode, ModeQuestion
from synthsurvey.questionnaire.schema import DONT_KNOW_CODE, Question, QuestionType

AnswerValue = Any  # str | float | int | list[str] | dict[str, Any] | None


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    DONT_KNOW = "dont_know"
    NONRESPONSE = "nonresponse"  # mostrata ma senza risposta valida
    NOT_APPLICABLE = "not_applicable"  # saltata dal routing o dal segmento
    ABANDONED = "abandoned"  # intervista interrotta prima di questa domanda


@dataclass
class AnswerRecord:
    run_id: str
    persona_id: str
    segment: str
    mode: str
    replicate: int
    model: str
    question_id: str
    item_id: str | None
    status: AnswerStatus
    answer_code: str | None = None
    answer_text: str | None = None
    option_order: list[str] | None = None
    clarification_requested: bool = False
    item_nonresponse: bool = False
    nonverbal_emitted: dict[str, Any] | None = None
    nonverbal_observed: dict[str, Any] | None = None
    incongruence: bool | None = None
    probe: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    page: int | None = None
    position: int = 0  # ordine di presentazione nell'intervista

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class InterviewOutcome:
    """Esito complessivo di un'intervista."""

    completed: bool
    abandoned_at: str | None = None  # id della prima domanda non raggiunta
    abandon_reason: str | None = None
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    refusals: int = 0
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Codifica
# --------------------------------------------------------------------------- #


def is_dont_know(value: AnswerValue) -> bool:
    return value in (DONT_KNOW_CODE, DONT_KNOW_LABEL)


def code_value(q: Question, value: AnswerValue, item_id: str | None = None) -> str | None:
    """Codice stabile per il dataset: indice 1-based nell'ordine canonico delle opzioni."""
    if value is None:
        return None
    if is_dont_know(value):
        return DONT_KNOW_CODE
    if q.type in (QuestionType.SINGLE, QuestionType.MULTI) or (
        q.type == QuestionType.GRID and q.options is not None
    ):
        options = q.options or []
        if isinstance(value, list):
            codici = [str(options.index(v) + 1) for v in value if v in options]
            return "|".join(codici) if codici else None
        return str(options.index(value) + 1) if value in options else None
    if q.type in (QuestionType.SCALE, QuestionType.NUMERIC) or q.type == QuestionType.GRID:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return f"{value:g}"
    return None


def text_value(value: AnswerValue) -> str | None:
    if value is None:
        return None
    if is_dont_know(value):
        return DONT_KNOW_LABEL
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    if isinstance(value, dict):
        return None
    return str(value)


def status_for(value: AnswerValue, *, open_question: bool = False) -> AnswerStatus:
    if value is None or (open_question and isinstance(value, str) and not value.strip()):
        return AnswerStatus.NONRESPONSE
    if is_dont_know(value):
        return AnswerStatus.DONT_KNOW
    if isinstance(value, list) and not value:
        return AnswerStatus.NONRESPONSE
    return AnswerStatus.ANSWERED


def routing_value(value: AnswerValue) -> AnswerValue:
    """Valore come lo vede `routing.evaluate`: "non so" diventa il codice canonico."""
    if is_dont_know(value):
        return DONT_KNOW_CODE
    if isinstance(value, dict):
        return {k: routing_value(v) for k, v in value.items()}
    return value


def mode_question_key(mq: ModeQuestion) -> tuple[str, str | None]:
    """(id domanda sorgente, id item) di una domanda adattata."""
    return mq.source_id, mq.item_id


def label_for_mode(mode: Mode) -> str:
    return {Mode.CAWI: "CAWI", Mode.CATI: "CATI", Mode.CAPI: "CAPI"}[mode]
