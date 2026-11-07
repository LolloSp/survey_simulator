"""Dataset largo: una riga per persona x modalità x replica x modello.

Convenzioni (riportate nel codebook):

- singola: codice numerico 1..k nell'ordine canonico delle opzioni;
- multipla: una variabile 0/1 per opzione, `<id>_<n>`;
- scala e numerica: il valore;
- griglia: una variabile per item, `<id>_<item>`;
- aperta: testo;
- mancanti con codici negativi: -1 non applicabile (routing o segmento),
  -2 non risposta, -3 "non so", -4 abbandono. Nelle aperte il testo è vuoto
  e il motivo sta nella colonna `<id>_status`.
"""

from dataclasses import dataclass
from typing import Any

import polars as pl

from synthsurvey.interview.records import AnswerStatus
from synthsurvey.questionnaire.schema import DONT_KNOW_CODE, Question, Questionnaire, QuestionType

MISSING = {
    AnswerStatus.NOT_APPLICABLE: -1,
    AnswerStatus.NONRESPONSE: -2,
    AnswerStatus.DONT_KNOW: -3,
    AnswerStatus.ABANDONED: -4,
}
MISSING_LABELS = {
    -1: "Non applicabile",
    -2: "Non risposta",
    -3: "Non so / preferisco non rispondere",
    -4: "Abbandono",
}
KEY_COLUMNS = ["persona_id", "mode", "replicate", "model"]
PERSONA_COLUMNS = [
    "segment",
    "region",
    "macro_area",
    "sex",
    "age",
    "age_band",
    "education",
    "employment",
    "income_quintile",
    "sector",
    "size_class",
    "respondent_role",
    "weight",
    "weight_pop",
]


@dataclass(frozen=True)
class WideVariable:
    name: str
    question_id: str
    item_id: str | None
    option_index: int | None  # per le dummy delle multiple (1-based)
    kind: str  # single | multi_dummy | scale | numeric | grid | open | status
    label: str
    values: dict[int, str]  # etichette dei valori (vuoto per numeriche e aperte)


def _label(q: Question, extra: str | None = None) -> str:
    testo = q.text if len(q.text) <= 200 else q.text[:197] + "..."
    return f"{testo} [{extra}]" if extra else testo


def wide_variables(questionnaire: Questionnaire) -> list[WideVariable]:
    """Variabili del dataset largo nell'ordine del questionario."""
    out: list[WideVariable] = []
    for q in questionnaire.questions:
        if q.type == QuestionType.SINGLE and q.options:
            valori = {i + 1: o for i, o in enumerate(q.options)}
            out.append(WideVariable(q.id, q.id, None, None, "single", _label(q), valori))
        elif q.type == QuestionType.MULTI and q.options:
            for i, o in enumerate(q.options, start=1):
                out.append(
                    WideVariable(
                        f"{q.id}_{i}",
                        q.id,
                        None,
                        i,
                        "multi_dummy",
                        _label(q, o),
                        {0: "Non scelta", 1: "Scelta"},
                    )
                )
        elif q.type == QuestionType.SCALE and q.scale:
            valori = {k: v for k, v in q.scale.labels.items()}
            out.append(WideVariable(q.id, q.id, None, None, "scale", _label(q), valori))
        elif q.type == QuestionType.GRID and q.items:
            if q.scale:
                valori = {k: v for k, v in q.scale.labels.items()}
            else:
                valori = {i + 1: o for i, o in enumerate(q.options or [])}
            for item in q.items:
                out.append(
                    WideVariable(
                        f"{q.id}_{item.id}",
                        q.id,
                        item.id,
                        None,
                        "grid",
                        _label(q, item.text),
                        valori,
                    )
                )
        elif q.type == QuestionType.NUMERIC:
            out.append(WideVariable(q.id, q.id, None, None, "numeric", _label(q), {}))
        elif q.type == QuestionType.OPEN:
            out.append(WideVariable(q.id, q.id, None, None, "open", _label(q), {}))
            out.append(
                WideVariable(
                    f"{q.id}_status",
                    q.id,
                    None,
                    None,
                    "status",
                    _label(q, "stato"),
                    {0: "Risposta", **MISSING_LABELS},
                )
            )
    return out


def _cell_value(var: WideVariable, status: str, code: str | None, text: str | None) -> Any:
    st = AnswerStatus(status)
    if var.kind == "open":
        return text if st is AnswerStatus.ANSWERED else ""
    if var.kind == "status":
        return 0 if st is AnswerStatus.ANSWERED else MISSING[st]
    if st is not AnswerStatus.ANSWERED:
        return MISSING[st]
    if code is None or code == DONT_KNOW_CODE:
        return MISSING[AnswerStatus.NONRESPONSE]
    if var.kind == "multi_dummy":
        scelte = {int(c) for c in code.split("|") if c}
        return 1 if var.option_index in scelte else 0
    if var.kind in ("single", "grid", "scale"):
        return int(float(code))
    if var.kind == "numeric":
        return float(code)
    return None


def build_wide(
    long: pl.DataFrame, personas: pl.DataFrame, questionnaire: Questionnaire
) -> tuple[pl.DataFrame, list[WideVariable]]:
    """Dal dataset lungo al largo, con gli attributi della persona e i pesi."""
    variables = wide_variables(questionnaire)
    by_name: dict[tuple[str, str | None], list[WideVariable]] = {}
    for v in variables:
        by_name.setdefault((v.question_id, v.item_id), []).append(v)
    righe: dict[tuple[Any, ...], dict[str, Any]] = {}
    cols = ["persona_id", "mode", "replicate", "model", "question_id", "item_id", "status"]
    cols += ["answer_code", "answer_text"]
    for r in long.select(cols).iter_rows(named=True):
        chiave = (r["persona_id"], r["mode"], r["replicate"], r["model"])
        riga = righe.setdefault(chiave, dict(zip(KEY_COLUMNS, chiave, strict=True)))
        for var in by_name.get((r["question_id"], r["item_id"]), []):
            riga[var.name] = _cell_value(var, r["status"], r["answer_code"], r["answer_text"])
    schema: dict[str, Any] = {"persona_id": pl.String, "mode": pl.String}
    schema["replicate"] = pl.Int64
    schema["model"] = pl.String
    for v in variables:
        schema[v.name] = (
            pl.String if v.kind == "open" else (pl.Float64 if v.kind == "numeric" else pl.Int64)
        )
    dati = [{**{k: None for k in schema}, **riga} for riga in righe.values()]
    wide = pl.DataFrame(dati, schema=schema) if dati else pl.DataFrame(schema=schema)
    attributi = [c for c in PERSONA_COLUMNS if c in personas.columns]
    wide = wide.join(personas.select(["persona_id", *attributi]), on="persona_id", how="left")
    ordine = KEY_COLUMNS + attributi + [v.name for v in variables]
    return wide.select(ordine).sort(KEY_COLUMNS), variables
