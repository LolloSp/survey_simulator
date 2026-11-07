"""Esportazione del dataset largo in formato SPSS (.sav) con etichette e codici mancanti."""

from pathlib import Path
from typing import Any, cast

import polars as pl
import pyreadstat

from synthsurvey.output.codebook import KEY_LABELS, PERSONA_LABELS
from synthsurvey.output.wide import KEY_COLUMNS, MISSING_LABELS, PERSONA_COLUMNS, WideVariable


def sav_metadata(
    variables: list[WideVariable], columns: list[str]
) -> tuple[dict[str, str], dict[str, dict[Any, str]], dict[str, list[dict[str, Any]]]]:
    """Etichette di variabile, etichette dei valori e intervalli mancanti per pyreadstat."""
    labels: dict[str, str] = {}
    for c in columns:
        if c in KEY_LABELS:
            labels[c] = KEY_LABELS[c]
        elif c in PERSONA_LABELS:
            labels[c] = PERSONA_LABELS[c]
    value_labels: dict[str, dict[Any, str]] = {}
    missing: dict[str, list[dict[str, Any]]] = {}
    for v in variables:
        if v.name not in columns:
            continue
        labels[v.name] = v.label[:256]
        if v.kind == "open":
            continue
        valori: dict[Any, str] = {float(k): lab for k, lab in v.values.items()}
        if v.kind != "status":
            valori.update({float(k): lab for k, lab in MISSING_LABELS.items()})
            missing[v.name] = [{"lo": -4.0, "hi": -1.0}]
        if valori:
            value_labels[v.name] = valori
    return labels, value_labels, missing


def write_sav(wide: pl.DataFrame, variables: list[WideVariable], path: Path) -> Path:
    """Scrive il .sav; le stringhe restano stringhe, i codici sono numerici."""
    colonne = list(wide.columns)
    labels, value_labels, missing = sav_metadata(variables, colonne)
    df = wide.to_pandas()
    for c in df.columns:
        if c in (
            "persona_id",
            "mode",
            "model",
            *[v.name for v in variables if v.kind == "open"],
        ) or (c in PERSONA_COLUMNS and df[c].dtype == object):
            df[c] = df[c].fillna("").astype(str)
    pyreadstat.write_sav(
        df,
        str(path),
        file_label="synthsurvey: dati SIMULATI, non risposte reali",
        column_labels=[labels.get(c, c) for c in df.columns],
        variable_value_labels=value_labels,
        missing_ranges=cast(Any, missing),
    )
    return path


__all__ = ["KEY_COLUMNS", "sav_metadata", "write_sav"]
