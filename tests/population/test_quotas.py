"""Filtri, target di quota, sovracampionamento, celle piccole."""

from pathlib import Path
from typing import Any

import polars as pl
import pytest

from survey_simulator.config import parse_config
from survey_simulator.config.schema import SegmentConfig
from survey_simulator.config.sources import get_source
from survey_simulator.population import quotas as q
from survey_simulator.population.imprese import build_imprese
from survey_simulator.population.individui import IndividuiPopulation, build_individui
from survey_simulator.population.tables import IstatTables, load_tables
from tests.config.conftest import config_base

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
INDIVIDUI = get_source("istat_individui")
IMPRESE = get_source("istat_imprese")


@pytest.fixture(scope="module")
def tables() -> IstatTables:
    return load_tables(PROCESSED)


@pytest.fixture(scope="module")
def pop(tables: IstatTables) -> IndividuiPopulation:
    return build_individui(tables)


def segmento(nome: str, **override: Any) -> SegmentConfig:
    base = config_base()
    seg = base["sample"]["segments"][nome]
    seg.update(override)
    return parse_config(base).sample.segments[nome]


def test_resti_maggiori() -> None:
    assert q.largest_remainder({"a": 0.5, "b": 0.3, "c": 0.2}, 10) == {"a": 5, "b": 3, "c": 2}
    assert q.largest_remainder({"a": 0.5, "b": 0.3, "c": 0.2}, 7) == {"a": 4, "b": 2, "c": 1}
    assert sum(q.largest_remainder({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}, 100).values()) == 100
    with pytest.raises(q.QuotaError, match="nulle"):
        q.largest_remainder({"a": 0.0}, 5)


def test_filtro_eta_intero_e_parziale(pop: IndividuiPopulation) -> None:
    frame = pop.to_frame()
    solo_giovani = q.apply_filters(
        frame, segmento("consumer", filters={"age": [18, 24]}), INDIVIDUI, pop.ages
    )
    assert solo_giovani["age_group"].unique().to_list() == ["18_24"]
    fino_80 = q.apply_filters(
        frame, segmento("consumer", filters={"age": [18, 80]}), INDIVIDUI, pop.ages
    )
    assert "85_plus" not in fino_80["age_group"].to_list()
    pieno = frame.filter(pl.col("age_group") == "80_84")["count"].sum()
    parziale = fino_80.filter(pl.col("age_group") == "80_84")["count"].sum()
    assert 0 < parziale < pieno
    assert fino_80.filter(pl.col("age_group") == "75_79")["count"].sum() == pytest.approx(
        frame.filter(pl.col("age_group") == "75_79")["count"].sum()
    )


def test_filtro_territorio(pop: IndividuiPopulation) -> None:
    frame = pop.to_frame()
    out = q.apply_filters(
        frame, segmento("consumer", filters={"region": ["lombardia", "lazio"]}), INDIVIDUI, pop.ages
    )
    assert sorted(out["region"].unique().to_list()) == ["lazio", "lombardia"]
    out = q.apply_filters(
        frame, segmento("consumer", filters={"macro_area": ["isole"]}), INDIVIDUI, pop.ages
    )
    assert out["macro_area"].unique().to_list() == ["isole"]
    assert sorted(out["region"].unique().to_list()) == ["sardegna", "sicilia"]


def test_filtro_imprese(tables: IstatTables) -> None:
    frame = build_imprese(tables)
    out = q.apply_filters(
        frame,
        segmento("pmi", filters={"employees": [10, 249], "sectors": ["commercio"]}),
        IMPRESE,
        None,
    )
    assert sorted(out["size_class"].unique().to_list()) == ["media", "piccola"]
    assert out["sector"].unique().to_list() == ["commercio"]
    tutte = q.apply_filters(
        frame, segmento("pmi", filters={"employees": [1, 249], "sectors": "all"}), IMPRESE, None
    )
    assert "grande" not in tutte["size_class"].to_list()
    assert "micro" in tutte["size_class"].to_list()


def test_filtro_che_svuota(tables: IstatTables) -> None:
    frame = build_imprese(tables)
    with pytest.raises(q.QuotaError, match="escludono"):
        q.apply_filters(
            frame,
            segmento("pmi", filters={"sectors": ["industria"], "macro_area": ["isole"]}),
            IMPRESE,
            None,
        ).filter(pl.col("sector") == "nessuno").pipe(
            lambda df: q.apply_filters(df, segmento("pmi"), IMPRESE, None)
        )


def test_target_e_sovracampionamento(tables: IstatTables) -> None:
    frame = build_imprese(tables)
    seg = segmento("pmi")
    frame = q.apply_filters(frame, seg, IMPRESE, None)
    n = 30
    over = q.oversample_targets(frame, seg, IMPRESE, n)
    assert [t.variable for t in over] == ["size_class"]
    assert over[0].target_shares == {"micro": 0.4, "piccola": 0.35, "media": 0.25}
    assert over[0].targets == {"micro": 12, "piccola": 11, "media": 7}
    assert over[0].population_shares["micro"] > 0.9

    design = q.rake_frame(frame, over)
    assert design["count"].sum() == pytest.approx(frame["count"].sum())
    quote_design = q.population_shares(design, "size_class", ("micro", "piccola", "media"))
    assert quote_design == pytest.approx({"micro": 0.4, "piccola": 0.35, "media": 0.25}, abs=1e-9)

    targets = q.quota_targets(frame, design, seg, IMPRESE, n)
    assert [t.variable for t in targets] == ["size_class", "sector"]
    settore = targets[1]
    assert not settore.oversampled
    assert sum(settore.targets.values()) == n
    assert sum(settore.population_shares.values()) == pytest.approx(1.0)
    # Nella popolazione di disegno le medie imprese pesano di più: l'industria sale.
    assert settore.target_shares["industria"] > settore.population_shares["industria"]


def test_sovracampionamento_su_categoria_assente(tables: IstatTables) -> None:
    frame = build_imprese(tables)
    seg = segmento(
        "pmi",
        filters={"employees": [10, 249], "sectors": "all"},
        oversample={"size_class": {"micro": 0.5, "piccola": 0.5}},
    )
    frame = q.apply_filters(frame, seg, IMPRESE, None)
    with pytest.raises(q.QuotaError, match="assenti"):
        q.oversample_targets(frame, seg, IMPRESE, 30)


def test_avvisi_celle_piccole(tables: IstatTables) -> None:
    frame = q.apply_filters(build_imprese(tables), segmento("pmi"), IMPRESE, None)
    targets = q.quota_targets(frame, frame, segmento("pmi", oversample={}), IMPRESE, 20)
    avvisi = q.small_cell_warnings(targets, 20, "pmi")
    assert any(a.startswith("pmi.size_class") and "media=" in a for a in avvisi)
    assert q.small_cell_warnings(targets, 100_000, "pmi") == []
