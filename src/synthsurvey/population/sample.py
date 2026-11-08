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
    QuotaError,
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

CONTACTS_SOURCE = "lista_clienti"

UNIT_COLUMNS = [
    "unit_id",
    "segment",
    "source",
    "unit_kind",
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
    # Solo per le anagrafiche (M13): cosa viene dal file e cosa da ISTAT.
    "province",
    "respondent_role_known",
    "sex_known",
    "age_known",
    "sector_known",
    "size_known",
]
UNIT_DTYPES: dict[str, type[pl.DataType]] = {
    "sex_known": pl.Boolean,
    "age_known": pl.Boolean,
    "sector_known": pl.Boolean,
    "size_known": pl.Boolean,
    "age": pl.Int64,
    "weight": pl.Float64,
    "weight_pop": pl.Float64,
}


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
    private_map: pl.DataFrame | None = None  # anagrafiche: unit_id -> record (non condivisibile)


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
        pl.lit(source.unit).alias("unit_kind"),
    )
    return units


def _sizes(
    config: SynthSurveyConfig, totals: dict[str, float], n_total: int | None
) -> dict[str, int]:
    n = n_total if n_total is not None else config.sample.total
    if n is None:
        raise QuotaError("sample.total mancante: obbligatorio con le sorgenti ISTAT")
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
    if all(seg.source == CONTACTS_SOURCE for seg in segments.values()):
        return _build_from_contacts(config, tables, n_total)
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

    tutte = _complete_columns(pl.concat([r.units for r in results.values()], how="diagonal"))
    return SampleResult(
        project=config.project.name,
        seed=config.project.seed,
        segments=results,
        units=tutte,
        ipf_iterations=individui.ipf.iterations if individui is not None else 0,
        ipf_max_rel_error=individui.ipf.max_rel_error if individui is not None else 0.0,
        warnings=warnings,
    )


def _complete_columns(units: pl.DataFrame) -> pl.DataFrame:
    for col in UNIT_COLUMNS:
        if col not in units.columns:
            units = units.with_columns(
                pl.lit(None, dtype=UNIT_DTYPES.get(col, pl.String)).alias(col)
            )
    return units.select(UNIT_COLUMNS)


def _build_from_contacts(
    config: SynthSurveyConfig, tables: IstatTables, n_total: int | None
) -> SampleResult:
    """Campione dalle anagrafiche (M13): un'unità per record valido, peso 1.

    `n_total` (pilota) prende i primi record di ogni segmento in proporzione.
    """
    from synthsurvey.population.contacts import load_contacts
    from synthsurvey.population.contacts_sample import (
        build_contacts_units,
        empty_draw,
        unit_weights,
    )

    segments = config.sample.segments
    letti = {}
    for name, seg in segments.items():
        assert seg.contacts is not None
        letti[name] = load_contacts(
            seg.contacts.path,
            unit=seg.contacts.unit,
            sheet=seg.contacts.sheet,
            mapping=seg.contacts.mapping or None,
            keep=seg.contacts.keep or None,
        )
    serve_individui = any((r.records["unit"] == "individui").any() for r in letti.values() if r.n)
    individui = build_individui(tables) if serve_individui else None
    quote: dict[str, int] | None = None
    if n_total is not None:
        totali = {n: (segments[n].size or r.n) for n, r in letti.items()}
        somma = sum(totali.values()) or 1
        quote = largest_remainder({k: v / somma for k, v in totali.items()}, min(n_total, somma))
    seeds = np.random.SeedSequence(config.project.seed).spawn(len(segments))
    results: dict[str, SegmentSample] = {}
    warnings: list[str] = []
    mappe = []
    for (name, seg), seed in zip(segments.items(), seeds, strict=True):
        rng = np.random.default_rng(seed)
        contatti = letti[name]
        if contatti.n == 0:
            raise QuotaError(f"{name}: nessun record utilizzabile in {contatti.path}")
        size = seg.size
        if quote is not None:
            size = min(quote[name], contatti.n)
        seg_eff = seg.model_copy(update={"size": size}) if size != seg.size else seg
        costruite = build_contacts_units(name, seg_eff, contatti, individui, tables, rng)
        avvisi = list(costruite.warnings)
        scarti = len(contatti.rejected)
        if scarti:
            avvisi.append(f"{name}: {scarti} record scartati dall'anagrafica (vedi rapporto)")
        if contatti.duplicates:
            avvisi.append(f"{name}: {contatti.duplicates} righe duplicate ignorate")
        n = costruite.units.height
        results[name] = SegmentSample(
            name=name,
            source=CONTACTS_SOURCE,
            n=n,
            population_total=float(contatti.n),
            targets=[],
            draw=empty_draw(n),
            weights=unit_weights(n),
            units=costruite.units,
            warnings=avvisi,
        )
        warnings.extend(avvisi)
        mappe.append(costruite.private_map)
    tutte = _complete_columns(pl.concat([r.units for r in results.values()], how="diagonal"))
    return SampleResult(
        project=config.project.name,
        seed=config.project.seed,
        segments=results,
        units=tutte,
        ipf_iterations=individui.ipf.iterations if individui is not None else 0,
        ipf_max_rel_error=individui.ipf.max_rel_error if individui is not None else 0.0,
        warnings=warnings,
        private_map=pl.concat(mappe) if mappe else None,
    )
