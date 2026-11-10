"""Filtri di segmento, target di quota, sovracampionamento e celle piccole."""

from dataclasses import dataclass
from math import floor

import numpy as np
import polars as pl

from survey_simulator.config.schema import SegmentConfig
from survey_simulator.config.sources import DataSource
from survey_simulator.population import categories as cat
from survey_simulator.population.individui import AGE_GROUPS, REGION_CODES, SEX
from survey_simulator.population.ipf import Array

MIN_CASI_PER_CELLA = 3
SIZE_CLASS_BOUNDS_ALL: dict[str, tuple[int, int]] = {
    **cat.SIZE_CLASS_BOUNDS,
    cat.SIZE_CLASS_LARGE: (250, 10**7),
}


class QuotaError(ValueError):
    """Filtri o quote che lasciano una popolazione vuota."""


@dataclass(frozen=True)
class QuotaTarget:
    variable: str
    population_shares: dict[str, float]  # quote nella popolazione filtrata
    target_shares: dict[str, float]  # quote usate per i target (oversample o popolazione)
    targets: dict[str, int]  # casi attesi per categoria, sommano a n
    oversampled: bool


# --------------------------------------------------------------------------- #
# Filtri
# --------------------------------------------------------------------------- #


def _age_fractions(ages: Array, lo: int, hi: int) -> pl.DataFrame:
    """Frazione di ogni gruppo quinquennale che cade in [lo, hi], per regione e sesso."""
    rows: list[tuple[str, str, str, float]] = []
    for ri, region in enumerate(REGION_CODES):
        for si, sex in enumerate(SEX):
            for label, glo, ghi in AGE_GROUPS:
                tot = ages[ri, si, glo : ghi + 1].sum()
                a, b = max(lo, glo), min(hi, ghi)
                dentro = ages[ri, si, a : b + 1].sum() if a <= b else 0.0
                rows.append((region, sex, label, float(dentro / tot) if tot > 0 else 0.0))
    return pl.DataFrame(
        rows, schema=["region_code", "sex", "age_group", "age_fraction"], orient="row"
    )


def apply_filters(
    frame: pl.DataFrame, seg: SegmentConfig, source: DataSource, ages: Array | None
) -> pl.DataFrame:
    """Azzera o riduce le celle escluse dai filtri del segmento.

    Età: i gruppi quinquennali parzialmente coperti vengono ridotti in
    proporzione alle età singole. Addetti: le classi che intersecano
    l'intervallo restano intere, perché dentro la classe non c'è dettaglio.
    """
    out = frame
    for name, value in seg.filters.items():
        if name == "age" and isinstance(value, tuple):
            if ages is None:
                raise QuotaError("filtro age senza popolazione per età")
            lo, hi = value
            fr = _age_fractions(ages, lo, hi)
            out = (
                out.join(fr, on=["region_code", "sex", "age_group"], how="left")
                .with_columns(
                    (pl.col("count") * pl.col("age_fraction").fill_null(0.0)).alias("count")
                )
                .drop("age_fraction")
            )
        elif name == "region" and isinstance(value, list):
            out = out.filter(pl.col("region").is_in(value))
        elif name == "macro_area" and isinstance(value, list):
            out = out.filter(pl.col("macro_area").is_in(value))
        elif name == "sectors" and isinstance(value, list):
            out = out.filter(pl.col("sector").is_in(value))
        elif name == "employees" and isinstance(value, tuple):
            lo, hi = value
            classi = [c for c, (a, b) in SIZE_CLASS_BOUNDS_ALL.items() if a <= hi and b >= lo]
            out = out.filter(pl.col("size_class").is_in(classi))
        # "all" e filtri sconosciuti (già respinti dalla config) non restringono.
    out = out.filter(pl.col("count") > 0)
    if out.is_empty():
        raise QuotaError(
            f"i filtri del segmento con sorgente {source.name} escludono tutta la popolazione"
        )
    return out


# --------------------------------------------------------------------------- #
# Target
# --------------------------------------------------------------------------- #


def largest_remainder(shares: dict[str, float], n: int) -> dict[str, int]:
    """Ripartisce n in interi proporzionali alle quote (metodo dei resti maggiori)."""
    tot = sum(shares.values())
    if tot <= 0:
        raise QuotaError("quote tutte nulle")
    raw = {k: n * v / tot for k, v in shares.items()}
    base = {k: floor(v) for k, v in raw.items()}
    resto = n - sum(base.values())
    ordine = sorted(shares, key=lambda k: (raw[k] - base[k], shares[k]), reverse=True)
    for k in ordine[:resto]:
        base[k] += 1
    return base


def frame_total(frame: pl.DataFrame) -> float:
    """Totale dei conteggi, sommato in numpy con ordine fisso (riproducibile bit a bit)."""
    return float(np.sum(frame["count"].to_numpy().astype(np.float64)))


def population_shares(
    frame: pl.DataFrame, variable: str, categories: tuple[str, ...]
) -> dict[str, float]:
    """Quote marginali di `variable` nel frame, arrotondate a 12 decimali.

    Le somme passano da numpy con ordine fisso: le riduzioni parallele di
    Polars cambiano l'ultimo bit fra un'esecuzione e l'altra e romperebbero la
    riproducibilità di target e pesi.
    """
    w = frame["count"].to_numpy().astype(np.float64)
    col = frame[variable].to_numpy().astype(str)
    tot = float(np.sum(w))
    return {c: round(float(np.sum(w[col == c])) / tot, 12) for c in categories}


def oversample_targets(
    frame: pl.DataFrame, seg: SegmentConfig, source: DataSource, n: int
) -> list[QuotaTarget]:
    """Target delle sole variabili sovracampionate (quote dalla config, non dalla popolazione)."""
    out: list[QuotaTarget] = []
    for var in seg.quotas:
        over = seg.oversample.get(var)
        if over is None:
            continue
        cats = source.quota_variables[var].categories
        pop = population_shares(frame, var, cats)
        target_shares = {c: float(over.get(c, 0.0)) for c in cats}
        impossibili = [c for c, s in target_shares.items() if s > 0 and pop[c] == 0]
        if impossibili:
            raise QuotaError(
                f"oversample.{var}: categorie assenti nella popolazione filtrata: "
                + ", ".join(impossibili)
            )
        out.append(
            QuotaTarget(
                variable=var,
                population_shares=pop,
                target_shares=target_shares,
                targets=largest_remainder(target_shares, n),
                oversampled=True,
            )
        )
    return out


def quota_targets(
    population: pl.DataFrame,
    design: pl.DataFrame,
    seg: SegmentConfig,
    source: DataSource,
    n: int,
) -> list[QuotaTarget]:
    """Target di tutte le variabili di quota, nell'ordine della config.

    `population` è la congiunta filtrata (quote vere, usate per i pesi);
    `design` è la stessa congiunta riallineata alle variabili sovracampionate:
    i target delle altre variabili vengono da qui, così il campione rispecchia
    la popolazione di disegno e i pesi tornano a quella reale senza conflitti.
    """
    over = {t.variable: t for t in oversample_targets(population, seg, source, n)}
    out: list[QuotaTarget] = []
    for var in seg.quotas:
        if var in over:
            out.append(over[var])
            continue
        cats = source.quota_variables[var].categories
        pop = population_shares(population, var, cats)
        design_shares = population_shares(design, var, cats)
        out.append(
            QuotaTarget(
                variable=var,
                population_shares=pop,
                target_shares=design_shares,
                targets=largest_remainder(design_shares, n),
                oversampled=False,
            )
        )
    return out


def small_cell_warnings(targets: list[QuotaTarget], n: int, segment: str) -> list[str]:
    avvisi: list[str] = []
    for t in targets:
        piccole = {c: n * s for c, s in t.target_shares.items() if 0 < n * s < MIN_CASI_PER_CELLA}
        if piccole:
            dettagli = ", ".join(f"{c}={v:.1f}" for c, v in piccole.items())
            avvisi.append(
                f"{segment}.{t.variable}: casi attesi sotto {MIN_CASI_PER_CELLA} per {dettagli}; "
                "valutare l'accorpamento delle categorie"
            )
    return avvisi


# --------------------------------------------------------------------------- #
# Sovracampionamento: riallinea la congiunta ai marginali richiesti
# --------------------------------------------------------------------------- #


def rake_frame(
    frame: pl.DataFrame, targets: list[QuotaTarget], *, max_iter: int = 200, tol: float = 1e-10
) -> pl.DataFrame:
    """Raking delle celle sui marginali `target_shares` delle variabili sovracampionate."""
    da_fare = [t for t in targets if t.oversampled]
    if not da_fare:
        return frame
    w = frame["count"].to_numpy().astype(np.float64).copy()
    totale = w.sum()
    cols = {t.variable: frame[t.variable].to_numpy() for t in da_fare}
    for _ in range(max_iter):
        worst = 0.0
        for t in da_fare:
            col = cols[t.variable]
            for c, share in t.target_shares.items():
                mask = col == c
                cur = w[mask].sum()
                tgt = share * totale
                if cur > 0:
                    w[mask] *= tgt / cur
                worst = max(worst, abs(cur - tgt) / totale)
        if worst < tol:
            break
    return frame.with_columns(pl.Series("count", w)).filter(pl.col("count") > 0)
