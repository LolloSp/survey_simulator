"""Aggregazioni per il report: distribuzioni, segmenti, effetti di modalità, stabilità.

Tutte le quote sono pesate con `weight` (somma pari alla numerosità del
campione) e calcolate sulle risposte valide; i mancanti sono riportati a
parte. Le funzioni restituiscono strutture semplici (dizionari e liste)
che il template del report e il modulo di validazione (M11) consumano.
"""

from dataclasses import dataclass, field
from typing import Any

import polars as pl

from synthsurvey.interview.records import AnswerStatus
from synthsurvey.output.wide import MISSING, WideVariable

VALID = pl.col("value") >= 0


def _f(x: object, default: float = 0.0) -> float:
    """Scalare polars in float (le medie di colonne booleane arrivano come oggetto)."""
    return float(x) if isinstance(x, int | float) else default


@dataclass
class Summary:
    name: str
    label: str
    kind: str
    n: int = 0  # risposte valide (non pesate)
    n_missing: int = 0
    mean: float | None = None
    shares: dict[str, float] = field(default_factory=dict)  # etichetta -> quota pesata
    missing_shares: dict[str, float] = field(default_factory=dict)


def _label_of(var: WideVariable, code: float) -> str:
    c = int(code) if float(code).is_integer() else code
    return var.values.get(int(c), str(c)) if isinstance(c, int) else str(c)


def summarize(
    wide: pl.DataFrame, var: WideVariable, *, weight: str = "weight", by: str | None = None
) -> dict[str, Summary]:
    """Riassunto di una variabile, globale (chiave "tutti") o per gruppo (`by`)."""
    if var.kind == "open" or var.name not in wide.columns:
        return {}
    cols = [var.name, weight] + ([by] if by else [])
    frame = wide.select(cols).rename({var.name: "value"})
    if weight not in wide.columns:
        frame = frame.with_columns(pl.lit(1.0).alias(weight))
    gruppi = (
        [(str(g), frame.filter(pl.col(by) == g)) for g in sorted(frame[by].drop_nulls().unique())]
        if by
        else [("tutti", frame)]
    )
    out: dict[str, Summary] = {}
    for nome, sub in gruppi:
        sub = sub.filter(pl.col("value").is_not_null())
        validi = sub.filter(VALID)
        s = Summary(
            var.name, var.label, var.kind, n=validi.height, n_missing=sub.height - validi.height
        )
        tot_w = float(validi[weight].sum()) if validi.height else 0.0
        if validi.height and var.kind in ("scale", "numeric", "grid", "multi_dummy"):
            s.mean = _f((validi["value"] * validi[weight]).sum()) / tot_w if tot_w else None
        if validi.height and var.kind in ("single", "scale", "grid", "multi_dummy", "status"):
            conte = validi.group_by("value").agg(pl.col(weight).sum().alias("w")).sort("value")
            s.shares = {
                _label_of(var, float(v)): round(float(w) / tot_w, 6) for v, w in conte.iter_rows()
            }
        mancanti = sub.filter(~VALID)
        if mancanti.height:
            conte = mancanti.group_by("value").agg(pl.len().alias("n")).sort("value")
            s.missing_shares = {
                _missing_label(int(v)): int(n) / sub.height for v, n in conte.iter_rows()
            }
        out[nome] = s
    return out


def _missing_label(code: int) -> str:
    from synthsurvey.output.wide import MISSING_LABELS

    return MISSING_LABELS.get(code, str(code))


def compare(
    wide: pl.DataFrame, variables: list[WideVariable], by: str, *, reference: str | None = None
) -> list[dict[str, Any]]:
    """Per ogni variabile, media o quota per gruppo e differenza rispetto al riferimento."""
    out = []
    for var in variables:
        if var.kind in ("open", "status"):
            continue
        per_gruppo = summarize(wide, var, by=by)
        if not per_gruppo:
            continue
        righe: dict[str, dict[str, Any]] = {}
        for g, s in per_gruppo.items():
            if var.kind == "single":
                top = max(s.shares.items(), key=lambda kv: kv[1]) if s.shares else (None, None)
                metrica, valore = f"quota «{top[0]}»" if top[0] else "quota", top[1]
            else:
                metrica, valore = "media", s.mean
            righe[g] = {
                "value": valore,
                "n": s.n,
                "missing_rate": s.n_missing / (s.n + s.n_missing) if (s.n + s.n_missing) else 0.0,
                "metric": metrica,
            }
        rif = reference if reference in righe else next(iter(righe))
        base = righe[rif]["value"]
        for r in righe.values():
            r["delta"] = (
                (r["value"] - base) if (r["value"] is not None and base is not None) else None
            )
        out.append(
            {
                "name": var.name,
                "label": var.label,
                "kind": var.kind,
                "reference": rif,
                "groups": righe,
            }
        )
    return out


def replicate_stability(wide: pl.DataFrame, variables: list[WideVariable]) -> list[dict[str, Any]]:
    """Quota di interviste (persona, modalità, modello) con risposta uguale in ogni replica."""
    out: list[dict[str, Any]] = []
    if wide["replicate"].n_unique() < 2:
        return out
    for var in variables:
        if var.kind in ("open", "status") or var.name not in wide.columns:
            continue
        sub = wide.select(["persona_id", "mode", "model", "replicate", var.name]).filter(
            pl.col(var.name) >= 0
        )
        if sub.height == 0:
            continue
        gruppi = sub.group_by(["persona_id", "mode", "model"]).agg(
            pl.col(var.name).n_unique().alias("distinti"), pl.len().alias("rep")
        )
        complete = gruppi.filter(pl.col("rep") >= 2)
        if complete.height == 0:
            continue
        accordo = _f((complete["distinti"] == 1).mean())
        out.append(
            {"name": var.name, "label": var.label, "agreement": accordo, "n": complete.height}
        )
    return out


def straightlining(wide: pl.DataFrame, variables: list[WideVariable]) -> list[dict[str, Any]]:
    """Per ogni griglia e modalità, quota di righe con lo stesso valore su tutti gli item."""
    griglie: dict[str, list[str]] = {}
    for v in variables:
        if v.kind == "grid":
            griglie.setdefault(v.question_id, []).append(v.name)
    out = []
    for qid, cols in griglie.items():
        if len(cols) < 2:
            continue
        sub = wide.select(["mode", *cols]).filter(pl.all_horizontal([pl.col(c) >= 0 for c in cols]))
        if sub.height == 0:
            continue
        uguale = pl.all_horizontal([pl.col(c) == pl.col(cols[0]) for c in cols[1:]]).alias("piatto")
        per_modo = (
            sub.with_columns(uguale)
            .group_by("mode")
            .agg(pl.col("piatto").mean().alias("quota"), pl.len().alias("n"))
            .sort("mode")
        )
        out.append(
            {
                "question_id": qid,
                "by_mode": {m: {"rate": float(q), "n": int(n)} for m, q, n in per_modo.iter_rows()},
            }
        )
    return out


def status_by_mode(long: pl.DataFrame) -> dict[str, dict[str, float]]:
    """Quote degli stati di risposta per modalità (sulle domande presentate)."""
    presentate = long.filter(pl.col("status") != AnswerStatus.NOT_APPLICABLE.value)
    out: dict[str, dict[str, float]] = {}
    for mode in sorted(presentate["mode"].unique().to_list()):
        sub = presentate.filter(pl.col("mode") == mode)
        conte = sub.group_by("status").agg(pl.len().alias("n"))
        out[mode] = {s: int(n) / sub.height for s, n in conte.iter_rows()} if sub.height else {}
    return out


def incongruence(long: pl.DataFrame, by: str) -> list[dict[str, Any]]:
    """Quota di risposte con incongruenza annotata dall'intervistatore, per `by`."""
    sub = long.filter(pl.col("mode").is_in(["cati", "capi"]) & pl.col("incongruence").is_not_null())
    if sub.height == 0:
        return []
    agg = (
        sub.group_by(by)
        .agg(pl.col("incongruence").mean().alias("rate"), pl.len().alias("n"))
        .sort(by)
    )
    return [{by: str(k), "rate": float(r), "n": int(n)} for k, r, n in agg.iter_rows()]


def probes_and_clarifications(long: pl.DataFrame) -> dict[str, dict[str, float]]:
    sub = long.filter(
        pl.col("mode").is_in(["cati", "capi"]) & (pl.col("status") != "not_applicable")
    )
    out: dict[str, dict[str, float]] = {}
    for mode in sorted(sub["mode"].unique().to_list()):
        m = sub.filter(pl.col("mode") == mode)
        out[mode] = {
            "clarification_rate": _f(m["clarification_requested"].mean()),
            "probe_rate": _f(m["probe"].mean()),
            "n": m.height,
        }
    return out


def open_answer_length(long: pl.DataFrame, open_ids: list[str]) -> dict[str, float]:
    sub = long.filter(pl.col("question_id").is_in(open_ids) & (pl.col("status") == "answered"))
    if sub.height == 0:
        return {}
    agg = sub.group_by("mode").agg(pl.col("answer_text").str.len_chars().mean().alias("chars"))
    return {m: float(c) for m, c in agg.sort("mode").iter_rows()}


def completion(long: pl.DataFrame) -> dict[str, float]:
    """Quota di interviste senza abbandono, per modalità."""
    out = {}
    for mode in sorted(long["mode"].unique().to_list()):
        sub = long.filter(pl.col("mode") == mode)
        per_int = sub.group_by(["persona_id", "replicate", "model"]).agg(
            (pl.col("status") == "abandoned").any().alias("abb")
        )
        out[mode] = 1.0 - _f(per_int["abb"].mean()) if per_int.height else 1.0
    return out


MISSING_CODES = MISSING
