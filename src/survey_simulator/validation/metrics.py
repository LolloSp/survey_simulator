"""Metriche di validazione ex post (docs/SPEC.md, "Congelamento e validazione").

- distanza fra distribuzioni per domanda: Jensen-Shannon (base 2, in
  [0, 1]) e variazione totale;
- correlazione fra medie o quote simulate e reali sull'insieme delle
  domande;
- coerenza delle differenze fra sottogruppi (segno e correlazione);
- direzione degli effetti di modalità, solo per le modalità osservate nel
  reale;
- intervalli di confidenza al 95% sul campione reale, per non scambiare
  rumore per errore del modello.
"""

import math
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from survey_simulator.output.wide import WideVariable
from survey_simulator.validation.real import mode_key

Z95 = 1.959964


@dataclass
class Distribution:
    shares: dict[int, float]  # codice -> quota pesata (solo validi)
    n: int
    mean: float | None
    sd: float | None


def distribution(frame: pl.DataFrame, var: str, weight: str = "weight") -> Distribution:
    sub = frame.select([var, weight]).filter(pl.col(var).is_not_null() & (pl.col(var) >= 0))
    if sub.height == 0:
        return Distribution({}, 0, None, None)
    w = sub[weight].cast(pl.Float64)
    v = sub[var].cast(pl.Float64)
    tot = float(w.sum())
    media = float((v * w).sum()) / tot if tot else None
    sd = None
    if sub.height > 1 and media is not None:
        var_w = float(((v - media) ** 2 * w).sum()) / tot
        sd = math.sqrt(var_w)
    conte = sub.group_by(var).agg(pl.col(weight).sum().alias("w")).sort(var)
    shares = {int(c): float(ww) / tot for c, ww in conte.iter_rows()} if tot else {}
    return Distribution(shares, sub.height, media, sd)


def js_divergence(p: dict[int, float], q: dict[int, float]) -> float | None:
    """Jensen-Shannon in base 2: 0 identiche, 1 disgiunte."""
    if not p or not q:
        return None
    chiavi = set(p) | set(q)
    m = {k: 0.5 * (p.get(k, 0.0) + q.get(k, 0.0)) for k in chiavi}

    def kl(a: dict[int, float]) -> float:
        return sum(
            a.get(k, 0.0) * math.log2(a.get(k, 0.0) / m[k]) for k in chiavi if a.get(k, 0.0) > 0
        )

    return 0.5 * kl(p) + 0.5 * kl(q)


def total_variation(p: dict[int, float], q: dict[int, float]) -> float | None:
    if not p or not q:
        return None
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in set(p) | set(q))


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / math.sqrt(sxx * syy)


def share_ci(p: float, n: int) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    se = math.sqrt(max(p * (1 - p), 0.0) / n)
    return (max(0.0, p - Z95 * se), min(1.0, p + Z95 * se))


def mean_ci(mean: float, sd: float | None, n: int) -> tuple[float, float]:
    if n <= 1 or sd is None:
        return (mean, mean)
    se = sd / math.sqrt(n)
    return (mean - Z95 * se, mean + Z95 * se)


@dataclass
class VariableComparison:
    name: str
    label: str
    kind: str
    n_real: int
    n_sim: int
    js: float | None
    tv: float | None
    metric: str  # "media" o "quota"
    real: float | None
    simulated: float | None
    ci_low: float | None
    ci_high: float | None
    within_ci: bool | None
    top_code: int | None = None

    @property
    def diff(self) -> float | None:
        if self.real is None or self.simulated is None:
            return None
        return self.simulated - self.real


def _headline(var: WideVariable, d: Distribution) -> tuple[str, float | None, int | None]:
    """Metrica di sintesi: media per scale/numeriche/griglie/dummy, quota modale per le singole."""
    if var.kind == "single":
        if not d.shares:
            return "quota", None, None
        top = max(d.shares.items(), key=lambda kv: kv[1])[0]
        return "quota", d.shares[top], top
    return "media", d.mean, None


def compare_variables(
    sim: pl.DataFrame, real: pl.DataFrame, variables: list[WideVariable], names: list[str]
) -> list[VariableComparison]:
    by_name = {v.name: v for v in variables}
    out = []
    for n in names:
        var = by_name[n]
        ds, dr = distribution(sim, n), distribution(real, n)
        metric, valore_r, top = _headline(var, dr)
        if metric == "quota":
            valore_s = ds.shares.get(top, 0.0) if top is not None and ds.shares else None
            ci = share_ci(valore_r, dr.n) if valore_r is not None else (None, None)
        else:
            valore_s = ds.mean
            ci = mean_ci(valore_r, dr.sd, dr.n) if valore_r is not None else (None, None)
        dentro = (
            ci[0] - 1e-9 <= valore_s <= ci[1] + 1e-9
            if valore_s is not None and ci[0] is not None and ci[1] is not None
            else None
        )
        out.append(
            VariableComparison(
                name=n,
                label=var.label,
                kind=var.kind,
                n_real=dr.n,
                n_sim=ds.n,
                js=js_divergence(ds.shares, dr.shares) if var.kind != "numeric" else None,
                tv=total_variation(ds.shares, dr.shares) if var.kind != "numeric" else None,
                metric=metric,
                real=valore_r,
                simulated=valore_s,
                ci_low=ci[0],
                ci_high=ci[1],
                within_ci=dentro,
                top_code=top,
            )
        )
    return out


def overall_correlation(comparisons: list[VariableComparison]) -> dict[str, Any]:
    """Correlazione fra i valori di sintesi simulati e reali; quote e medie separate."""
    out: dict[str, Any] = {}
    for metric in ("quota", "media"):
        coppie = [
            (c.simulated, c.real)
            for c in comparisons
            if c.metric == metric and c.simulated is not None and c.real is not None
        ]
        xs = [float(s) for s, _ in coppie]
        ys = [float(r) for _, r in coppie]
        out[metric] = {"n": len(coppie), "r": pearson(xs, ys)}
    return out


def subgroup_coherence(
    sim: pl.DataFrame,
    real: pl.DataFrame,
    variables: list[WideVariable],
    names: list[str],
    by: str,
) -> dict[str, Any]:
    """Differenze fra sottogruppi (rispetto al primo) in simulato e reale: segno e correlazione."""
    comuni = set(real[by].drop_nulls().unique().to_list()) & set(
        sim[by].drop_nulls().unique().to_list()
    )
    gruppi = sorted(comuni, key=mode_key) if by == "mode" else sorted(comuni)
    if len(gruppi) < 2:
        return {"by": by, "groups": gruppi, "n": 0, "sign_agreement": None, "r": None}
    base = gruppi[0]
    by_name = {v.name: v for v in variables}
    diff_s: list[float] = []
    diff_r: list[float] = []
    for n in names:
        var = by_name[n]
        if var.kind == "single":
            continue
        for g in gruppi[1:]:
            ms = distribution(sim.filter(pl.col(by) == g), n).mean
            mb = distribution(sim.filter(pl.col(by) == base), n).mean
            rs = distribution(real.filter(pl.col(by) == g), n).mean
            rb = distribution(real.filter(pl.col(by) == base), n).mean
            if None in (ms, mb, rs, rb):
                continue
            assert ms is not None and mb is not None and rs is not None and rb is not None
            diff_s.append(ms - mb)
            diff_r.append(rs - rb)
    if not diff_s:
        return {"by": by, "groups": gruppi, "n": 0, "sign_agreement": None, "r": None}
    segni = [
        1.0 if (a > 0) == (b > 0) or (a == 0 and b == 0) else 0.0
        for a, b in zip(diff_s, diff_r, strict=True)
    ]
    return {
        "by": by,
        "groups": gruppi,
        "n": len(diff_s),
        "sign_agreement": sum(segni) / len(segni),
        "r": pearson(diff_s, diff_r),
    }


def mode_effect_direction(
    sim: pl.DataFrame,
    real: pl.DataFrame,
    variables: list[WideVariable],
    names: list[str],
    modes: list[str],
) -> dict[str, Any]:
    """Per le modalità osservate nel reale: differenze rispetto alla prima, segno e correlazione."""
    if len(modes) < 2:
        return {"modes": modes, "n": 0, "sign_agreement": None, "r": None, "pairs": []}
    return {
        **subgroup_coherence(sim, real, variables, names, "mode"),
        "modes": modes,
    }


@dataclass
class ValidationResult:
    alignment: Any
    comparisons: list[VariableComparison]
    correlation: dict[str, Any]
    subgroups: list[dict[str, Any]]
    mode_effects: dict[str, Any]
    summary: dict[str, Any] = field(default_factory=dict)


def summarize_result(result: ValidationResult) -> dict[str, Any]:
    comp = result.comparisons
    js = [c.js for c in comp if c.js is not None]
    tv = [c.tv for c in comp if c.tv is not None]
    dentro = [c.within_ci for c in comp if c.within_ci is not None]
    return {
        "variables": len(comp),
        "js_mean": sum(js) / len(js) if js else None,
        "tv_mean": sum(tv) / len(tv) if tv else None,
        "within_ci_share": sum(1 for d in dentro if d) / len(dentro) if dentro else None,
        "r_quote": result.correlation.get("quota", {}).get("r"),
        "r_medie": result.correlation.get("media", {}).get("r"),
        "mode_sign_agreement": result.mode_effects.get("sign_agreement"),
    }
