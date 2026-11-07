"""Schemi JSON delle risposte strutturate e normalizzazione di ciò che il modello restituisce.

Gli schemi usano solo costrutti accettati dall'output strutturato dei
provider (type, enum, anyOf, properties, required, additionalProperties,
items): niente minimum/maximum, che vengono controllati qui dopo.
"""

from typing import Any

from synthsurvey.interview.records import AnswerValue, is_dont_know
from synthsurvey.questionnaire.modes import DONT_KNOW_LABEL, ModeQuestion
from synthsurvey.questionnaire.schema import DONT_KNOW_CODE, QuestionType

_NULL = {"type": "null"}


def _with_dont_know(schema: dict[str, Any], mq: ModeQuestion) -> dict[str, Any]:
    """Aggiunge il "non so" come alternativa se la domanda lo ammette."""
    if not mq.dont_know:
        return schema
    return {"anyOf": [schema, {"type": "string", "enum": [DONT_KNOW_LABEL]}]}


def value_schema(mq: ModeQuestion, options: list[str] | None = None) -> dict[str, Any]:
    """Schema del valore di risposta per una domanda adattata.

    `options` è l'ordine presentato (senza l'etichetta "non so", che viene
    aggiunta qui se la domanda lo ammette).
    """
    presented = [o for o in (options if options is not None else (mq.options or []))]
    presented = [o for o in presented if o != DONT_KNOW_LABEL]
    if mq.type == QuestionType.SINGLE:
        return _with_dont_know({"type": "string", "enum": presented}, mq)
    if mq.type == QuestionType.MULTI:
        return _with_dont_know(
            {"type": "array", "items": {"type": "string", "enum": presented}}, mq
        )
    if mq.type == QuestionType.SCALE:
        assert mq.scale is not None
        return _with_dont_know({"type": "integer", "enum": mq.scale.points}, mq)
    if mq.type == QuestionType.NUMERIC:
        return _with_dont_know({"type": "number"}, mq)
    if mq.type == QuestionType.OPEN:
        return {"type": "string"}
    if mq.type == QuestionType.GRID:
        assert mq.items is not None
        if mq.scale is not None:
            cella: dict[str, Any] = {"type": "integer", "enum": mq.scale.points}
        else:
            cella = {"type": "string", "enum": presented}
        cella = _with_dont_know(cella, mq)
        return {
            "type": "object",
            "properties": {iid: cella for iid, _ in mq.items},
            "required": [iid for iid, _ in mq.items],
            "additionalProperties": False,
        }
    raise ValueError(f"tipo di domanda non gestito: {mq.type}")


def normalize_value(mq: ModeQuestion, raw: Any, options: list[str] | None = None) -> AnswerValue:
    """Porta la risposta del modello nel formato interno; `None` se non codificabile.

    Controlla ciò che lo schema non può: numeri nei limiti, al massimo
    `max_choices` scelte, etichette fra quelle presentate, "non so" ammesso.
    """
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip() in (DONT_KNOW_LABEL, DONT_KNOW_CODE):
        return DONT_KNOW_CODE if mq.dont_know else None
    presented = [o for o in (options if options is not None else (mq.options or []))]
    presented = [o for o in presented if o != DONT_KNOW_LABEL]
    t = mq.type
    if t == QuestionType.SINGLE:
        return raw if isinstance(raw, str) and raw in presented else None
    if t == QuestionType.MULTI:
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return None
        scelte: list[str] = []
        for v in raw:
            if isinstance(v, str) and v in presented and v not in scelte:
                scelte.append(v)
        if mq.max_choices is not None and len(scelte) > mq.max_choices:
            scelte = scelte[: mq.max_choices]
        return scelte or None
    if t == QuestionType.SCALE:
        assert mq.scale is not None
        n = _as_number(raw)
        if n is None or int(n) != n or int(n) not in mq.scale.points:
            return None
        return int(n)
    if t == QuestionType.NUMERIC:
        n = _as_number(raw)
        if n is None:
            return None
        if mq.numeric_min is not None and n < mq.numeric_min:
            return None
        if mq.numeric_max is not None and n > mq.numeric_max:
            return None
        return n
    if t == QuestionType.OPEN:
        return raw.strip() if isinstance(raw, str) and raw.strip() else None
    if t == QuestionType.GRID:
        assert mq.items is not None
        if not isinstance(raw, dict):
            return None
        out: dict[str, AnswerValue] = {}
        for iid, _ in mq.items:
            v = raw.get(iid)
            if isinstance(v, str) and v.strip() in (DONT_KNOW_LABEL, DONT_KNOW_CODE):
                out[iid] = DONT_KNOW_CODE if mq.dont_know else None
            elif mq.scale is not None:
                n = _as_number(v)
                out[iid] = (
                    int(n) if n is not None and int(n) == n and int(n) in mq.scale.points else None
                )
            else:
                out[iid] = v if isinstance(v, str) and v in presented else None
        return out


def _as_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", ".").strip())
        except ValueError:
            return None
    return None


def grid_complete(value: AnswerValue) -> bool:
    return isinstance(value, dict) and all(v is not None for v in value.values())


def describe_value(value: AnswerValue) -> str:
    """Testo breve per i log e le trascrizioni."""
    if value is None:
        return "(nessuna risposta)"
    if is_dont_know(value):
        return DONT_KNOW_LABEL
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}={describe_value(v)}" for k, v in value.items())
    return str(value)
