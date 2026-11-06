"""Costruzione del campione: popolazione sintetica, filtri, quote, estrazione, pesi."""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl

from synthsurvey.config.rules import segment_sizes
from synthsurvey.config.schema import Allocation, SegmentConfig, SynthSurveyConfig
from synthsurvey.config.sources import DataSource, get_source
from synthsurvey.population.imprese import build_imprese
from synthsurvey.population.individui import (
    AGE_GROUPS,
    REGION_CODES,
    SEX,
    IndividuiPopulation,
    build_individui,
)
from synthsurvey.population.ipf import Array
from synthsurvey.population.quotas import (
    QuotaTarget,
    apply_filters,
    frame_total,
    largest_remainder,
    oversample_targets,
    quota_targets,
    rake_frame,
    small_cell_warnings,
)
from synthsurvey.population.sampling import DrawResult, draw_cells, expand_units
from synthsurvey.population.tables import IstatTables, load_tables
from synthsurvey.population.weights import WeightResult, rake_weights

UNIT_COLUMNS = [
    "unit_id",
    "segment",
    "source",
    "region_code",
    "region",
    "macro_area",
    "sex",
    "age",
    "age_band",
    "education",
    "employment",
    "sector",
    "size_class",
    "weight",
    "weight_pop",
]


@dataclass(frozen=True)
class SegmentSample:
    name: str
    source: str
    n: int
    population_total: float
    targets: list[QuotaTarget]
    draw: DrawResult
    weights: WeightResult
    units: pl.DataFrame
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SampleResult:
    project: str
    seed: int
    segments: dict[str, SegmentSample]
    units: pl.DataFrame
    ipf_iterations: int
    ipf_max_rel_error: float
    warnings: list[str]


def _frame_for(
    source: DataSource, individui: IndividuiPopulation | None, tables: IstatTables
) -> pl.DataFrame:
    if source.unit == "individui":
        if individui is None:
            raise AssertionError("popolazione individui non costruita")
        return individui.to_frame()
    return build_imprese(tables)


def _draw_ages(
    units: pl.DataFrame, ages: Array, seg: SegmentConfig, rng: np.random.Generator
) -> pl.Series:
    """Età puntuale per unità, proporzionale alle età singole del gruppo, entro il filtro età."""
    lo_f, hi_f = 18, 100
    age_filter = seg.filters.get("age")
    if isinstance(age_filter, tuple):
        lo_f, hi_f = age_filter
    bounds = {label: (lo, hi) for label, lo, hi in AGE_GROUPS}
    region_idx = {c: i for i, c in enumerate(REGION_CODES)}
    sex_idx = {s: i for i, s in enumerate(SEX)}
    out: list[int] = []
    for rc, sx, grp in zip(
        units["region_code"].to_list(),
        units["sex"].to_list(),
        units["age_group"].to_list(),
        strict=True,
    ):
        glo, ghi = bounds[grp]
        a, b = max(glo, lo_f), min(ghi, hi_f)
        candidate = np.arange(a, b + 1)
        p = ages[region_idx[rc], sex_idx[sx], a : b + 1].astype(np.float64)
        p = p / p.sum() if p.sum() > 0 else np.full(len(candidate), 1.0 / len(candidate))
        out.append(int(rng.choice(candidate, p=p)))
    return pl.Series("age", out, dtype=pl.Int64)


def _segment_units(
    name: str,
    seg: SegmentConfig,
    source: DataSource,
    frame: pl.DataFrame,
    counts: np.ndarray,
    ages: Array | None,
    rng: np.random.Generator,
) -> pl.DataFrame:
    units = expand_units(frame, counts)
    if source.unit == "individui":
        if ages is None:
            raise AssertionError("età singole mancanti")
        units = units.with_columns(_draw_ages(units, ages, seg, rng)).drop("age_group")
    units = units.with_columns(
        pl.Series("unit_id", [f"{name}_{i + 1:05d}" for i in range(units.height)]),
        pl.lit(name).alias("segment"),
        pl.lit(source.name).alias("source"),
    )
    return units


def _sizes(
    config: SynthSurveyConfig, totals: dict[str, float], n_total: int | None
) -> dict[str, int]:
    n = n_total if n_total is not None else config.sample.total
    if config.sample.allocation is Allocation.PROPORTIONAL:
        shares = {k: v / sum(totals.values()) for k, v in totals.items()}
        return largest_remainder(shares, n)
    sizes = segment_sizes(config)
    if n_total is None:
        return sizes
    shares = {k: v / sum(sizes.values()) for k, v in sizes.items()}
    return largest_remainder(shares, n)


def build_sample(
    config: SynthSurveyConfig,
    processed_dir: Path,
    *,
    n_total: int | None = None,
    tables: IstatTables | None = None,
) -> SampleResult:
    """Costruisce il campione di tutti i segmenti della configurazione.

    `n_total` sostituisce `sample.total` (ad esempio per il pilota); le
    dimensioni dei segmenti seguono le stesse proporzioni. Ogni segmento usa
    un generatore derivato dal seed di progetto, in ordine di configurazione.
    """
    tables = tables if tables is not None else load_tables(processed_dir)
    segments = config.sample.segments
    sources = {name: get_source(seg.source) for name, seg in segments.items()}
    individui = (
        build_individui(tables) if any(s.unit == "individui" for s in sources.values()) else None
    )
    frames: dict[str, pl.DataFrame] = {}
    for name, seg in segments.items():
        source = sources[name]
        ages = individui.ages if individui is not None else None
        filtrato = apply_filters(_frame_for(source, individui, tables), seg, source, ages)
        frames[name] = filtrato.sort([c for c in filtrato.columns if c != "count"])
    totals = {name: frame_total(f) for name, f in frames.items()}
    sizes = _sizes(config, totals, n_total)

    seeds = np.random.SeedSequence(config.project.seed).spawn(len(segments))
    results: dict[str, SegmentSample] = {}
    warnings: list[str] = []
    for (name, seg), seed in zip(segments.items(), seeds, strict=True):
        source = sources[name]
        rng = np.random.default_rng(seed)
        n = sizes[name]
        frame = rake_frame(frames[name], oversample_targets(frames[name], seg, source, n))
        targets = quota_targets(frames[name], frame, seg, source, n)
        avvisi = small_cell_warnings(targets, n, name)
        draw = draw_cells(frame, n, targets, rng)
        if draw.max_deviation > 0:
            avvisi.append(
                f"{name}: marginali di quota con scarto massimo {draw.max_deviation} "
                f"dopo {draw.swaps} scambi"
            )
        ages = individui.ages if individui is not None else None
        units = _segment_units(name, seg, source, frame, draw.counts, ages, rng)
        weights = rake_weights(units, targets, totals[name])
        avvisi.extend(f"{name}: {w}" for w in weights.warnings)
        units = units.with_columns(
            pl.Series("weight", weights.weight), pl.Series("weight_pop", weights.weight_pop)
        )
        results[name] = SegmentSample(
            name=name,
            source=source.name,
            n=n,
            population_total=totals[name],
            targets=targets,
            draw=draw,
            weights=weights,
            units=units,
            warnings=avvisi,
        )
        warnings.extend(avvisi)

    tutte = pl.concat([r.units for r in results.values()], how="diagonal")
    for col in UNIT_COLUMNS:
        if col not in tutte.columns:
            tutte = tutte.with_columns(pl.lit(None, dtype=pl.String).alias(col))
    tutte = tutte.select(UNIT_COLUMNS)
    return SampleResult(
        project=config.project.name,
        seed=config.project.seed,
        segments=results,
        units=tutte,
        ipf_iterations=individui.ipf.iterations if individui is not None else 0,
        ipf_max_rel_error=individui.ipf.max_rel_error if individui is not None else 0.0,
        warnings=warnings,
    )
