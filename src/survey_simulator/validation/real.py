"""Importazione dei dati reali e allineamento al disegno del run.

Formato accettato (CSV, UTF-8):

- **lungo**: colonne `respondent_id`, `mode`, `question_id`, `answer_code`,
  facoltative `item_id`, `segment`, `weight`. `answer_code` usa le stesse
  convenzioni del dataset lungo simulato: indice 1..k per le singole,
  indici separati da `|` per le multiple, numero per scale e numeriche,
  `NS` per "non so", vuoto per non risposta;
- **largo**: una riga per rispondente, colonne con i nomi delle variabili
  del dataset largo simulato (`q1`, `q4_1`, `q5_a`, ...), più
  `respondent_id`, `mode` e facoltative `segment`, `weight`. I codici
  mancanti negativi sono ammessi.

In entrambi i casi il risultato è un dataset largo con le stesse variabili
del simulato, così le metriche confrontano colonne omonime.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from survey_simulator.interview.records import AnswerStatus
from survey_simulator.output.wide import MISSING, WideVariable, wide_variables
from survey_simulator.questionnaire.schema import DONT_KNOW_CODE, Questionnaire

REQUIRED_LONG = ("respondent_id", "mode", "question_id", "answer_code")
REQUIRED_WIDE = ("respondent_id", "mode")
MODE_ORDER = ("cawi", "cati", "capi")


def mode_key(mode: str) -> tuple[int, str]:
    return (MODE_ORDER.index(mode) if mode in MODE_ORDER else len(MODE_ORDER), mode)


class RealDataError(Exception):
    """File dei dati reali assente, malformato o non allineabile."""


@dataclass
class Alignment:
    modes: list[str]  # modalità presenti sia nel reale sia nel simulato
    real_only_modes: list[str]
    simulated_only_modes: list[str]
    variables: list[str]  # variabili confrontabili
    missing_in_real: list[str]
    segments: list[str]  # segmenti comuni, se il reale li riporta
    subgroup_columns: list[str]  # attributi presenti in entrambi
    n_real: int
    n_simulated: int
    warnings: list[str] = field(default_factory=list)


def _status_from_code(code: str | None) -> tuple[str, str | None]:
    if code is None or str(code).strip() == "":
        return AnswerStatus.NONRESPONSE.value, None
    c = str(code).strip()
    if c.upper() == DONT_KNOW_CODE:
        return AnswerStatus.DONT_KNOW.value, DONT_KNOW_CODE
    return AnswerStatus.ANSWERED.value, c


def long_to_wide_real(long: pl.DataFrame, questionnaire: Questionnaire) -> pl.DataFrame:
    """Dal formato lungo reale al largo con le variabili del simulato."""
    from survey_simulator.output.wide import _cell_value

    variables = wide_variables(questionnaire)
    by_key: dict[tuple[str, str | None], list[WideVariable]] = {}
    for v in variables:
        by_key.setdefault((v.question_id, v.item_id), []).append(v)
    has_item = "item_id" in long.columns
    extra = [c for c in ("segment", "weight") if c in long.columns]
    righe: dict[tuple[str, str], dict[str, Any]] = {}
    for r in long.iter_rows(named=True):
        chiave = (str(r["respondent_id"]), str(r["mode"]).lower())
        riga = righe.setdefault(chiave, {"respondent_id": chiave[0], "mode": chiave[1]})
        for c in extra:
            if r.get(c) is not None:
                riga[c] = r[c]
        item = r.get("item_id") if has_item else None
        item = None if item in (None, "") else str(item)
        status, code = _status_from_code(r.get("answer_code"))
        for var in by_key.get((str(r["question_id"]), item), []):
            riga[var.name] = _cell_value(var, status, code, None)
    schema: dict[str, Any] = {"respondent_id": pl.String, "mode": pl.String}
    if "segment" in extra:
        schema["segment"] = pl.String
    if "weight" in extra:
        schema["weight"] = pl.Float64
    for v in variables:
        if v.kind == "open":
            continue
        schema[v.name] = pl.Float64 if v.kind == "numeric" else pl.Int64
    dati = []
    for riga in righe.values():
        completa: dict[str, Any] = dict.fromkeys(schema)
        for k, v in riga.items():
            if k in schema and v is not None:
                completa[k] = v
        # Domande senza riga nel file: non applicabili.
        for v in variables:
            if v.kind != "open" and completa.get(v.name) is None:
                completa[v.name] = MISSING[AnswerStatus.NOT_APPLICABLE]
        dati.append(completa)
    return pl.DataFrame(dati, schema=schema)


def load_real(path: Path, questionnaire: Questionnaire) -> pl.DataFrame:
    """Legge il CSV reale (lungo o largo) e restituisce il largo allineato."""
    if not path.is_file():
        raise RealDataError(f"file dei dati reali non trovato: {path}")
    try:
        raw = pl.read_csv(path, infer_schema_length=None, encoding="utf8")
    except Exception as exc:  # polars solleva errori eterogenei
        raise RealDataError(f"CSV non leggibile: {exc}") from exc
    if set(REQUIRED_LONG) <= set(raw.columns):
        wide = long_to_wide_real(raw, questionnaire)
    elif set(REQUIRED_WIDE) <= set(raw.columns):
        wide = raw.with_columns(
            pl.col("respondent_id").cast(pl.String),
            pl.col("mode").cast(pl.String).str.to_lowercase(),
        )
        for v in wide_variables(questionnaire):
            if v.name in wide.columns and v.kind != "open":
                wide = wide.with_columns(
                    pl.col(v.name).cast(
                        pl.Float64 if v.kind == "numeric" else pl.Int64, strict=False
                    )
                )
    else:
        raise RealDataError(
            "colonne non riconosciute: servono "
            f"{', '.join(REQUIRED_LONG)} (formato lungo) oppure {', '.join(REQUIRED_WIDE)} "
            "più le variabili del largo (formato largo)"
        )
    if wide.height == 0:
        raise RealDataError("nessun rispondente nei dati reali")
    if "weight" not in wide.columns:
        wide = wide.with_columns(pl.lit(1.0).alias("weight"))
    else:
        wide = wide.with_columns(pl.col("weight").cast(pl.Float64, strict=False).fill_null(1.0))
    return wide


def align(simulated: pl.DataFrame, real: pl.DataFrame, variables: list[WideVariable]) -> Alignment:
    modes_sim = set(simulated["mode"].unique().to_list())
    modes_real = set(real["mode"].unique().to_list())
    comuni = sorted(modes_sim & modes_real, key=mode_key)
    nomi = [v.name for v in variables if v.kind not in ("open", "status")]
    presenti = [n for n in nomi if n in real.columns and real[n].drop_nulls().len() > 0]
    segmenti: list[str] = []
    if "segment" in real.columns and "segment" in simulated.columns:
        segmenti = sorted(
            set(real["segment"].drop_nulls().unique().to_list())
            & set(simulated["segment"].unique().to_list())
        )
    sottogruppi: list[str] = [
        c
        for c in ("segment", "age_band", "macro_area", "sex", "size_class", "education")
        if c in real.columns and c in simulated.columns and real[c].drop_nulls().len() > 0
    ]
    avvisi = []
    if not comuni:
        avvisi.append(
            "nessuna modalità in comune: il reale ha "
            f"{', '.join(sorted(modes_real))}, il simulato {', '.join(sorted(modes_sim))}"
        )
    if not presenti:
        avvisi.append("nessuna variabile confrontabile nei dati reali")
    return Alignment(
        modes=comuni,
        real_only_modes=sorted(modes_real - modes_sim, key=mode_key),
        simulated_only_modes=sorted(modes_sim - modes_real, key=mode_key),
        variables=presenti,
        missing_in_real=[n for n in nomi if n not in presenti],
        segments=segmenti,
        subgroup_columns=sottogruppi,
        n_real=real.height,
        n_simulated=simulated.height,
        warnings=avvisi,
    )
