"""Estrazione per quote e pesi: marginali esatti, determinismo, ricostruzione della popolazione."""

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from survey_simulator.config import parse_config
from survey_simulator.config.sources import get_source
from survey_simulator.population import quotas as q
from survey_simulator.population.individui import IndividuiPopulation, build_individui
from survey_simulator.population.sampling import draw_cells, expand_units
from survey_simulator.population.tables import IstatTables, load_tables
from survey_simulator.population.weights import rake_weights
from tests.config.conftest import config_base

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
INDIVIDUI = get_source("istat_individui")


@pytest.fixture(scope="module")
def tables() -> IstatTables:
    return load_tables(PROCESSED)


@pytest.fixture(scope="module")
def pop(tables: IstatTables) -> IndividuiPopulation:
    return build_individui(tables)


@pytest.fixture(scope="module")
def consumer_frame(pop: IndividuiPopulation) -> pl.DataFrame:
    seg = parse_config(config_base()).sample.segments["consumer"]
    return q.apply_filters(pop.to_frame(), seg, INDIVIDUI, pop.ages)


def targets_consumer(frame: pl.DataFrame, n: int) -> list[q.QuotaTarget]:
    seg = parse_config(config_base()).sample.segments["consumer"]
    return q.quota_targets(frame, frame, seg, INDIVIDUI, n)


def test_estrazione_rispetta_le_quote(consumer_frame: pl.DataFrame) -> None:
    n = 70
    targets = targets_consumer(consumer_frame, n)
    res = draw_cells(consumer_frame, n, targets, np.random.default_rng(1))
    assert res.counts.sum() == n
    assert res.max_deviation == 0
    for t in targets:
        assert res.achieved[t.variable] == t.targets
    units = expand_units(consumer_frame, res.counts)
    assert units.height == n
    assert "count" not in units.columns


def test_estrazione_deterministica(consumer_frame: pl.DataFrame) -> None:
    targets = targets_consumer(consumer_frame, 50)
    a = draw_cells(consumer_frame, 50, targets, np.random.default_rng(7))
    b = draw_cells(consumer_frame, 50, targets, np.random.default_rng(7))
    c = draw_cells(consumer_frame, 50, targets, np.random.default_rng(8))
    assert np.array_equal(a.counts, b.counts)
    assert not np.array_equal(a.counts, c.counts)


def test_estrazione_su_caso_giocattolo() -> None:
    frame = pl.DataFrame(
        {
            "x": ["a", "a", "b", "b"],
            "y": ["p", "q", "p", "q"],
            "count": [40.0, 10.0, 10.0, 40.0],
        }
    )
    targets = [
        q.QuotaTarget("x", {"a": 0.5, "b": 0.5}, {"a": 0.5, "b": 0.5}, {"a": 5, "b": 5}, False),
        q.QuotaTarget("y", {"p": 0.5, "q": 0.5}, {"p": 0.5, "q": 0.5}, {"p": 5, "q": 5}, False),
    ]
    res = draw_cells(frame, 10, targets, np.random.default_rng(0))
    assert res.max_deviation == 0
    assert res.achieved == {"x": {"a": 5, "b": 5}, "y": {"p": 5, "q": 5}}
    with pytest.raises(ValueError, match="positivo"):
        draw_cells(frame, 0, targets, np.random.default_rng(0))


def test_pesi_ricostruiscono_i_marginali(consumer_frame: pl.DataFrame) -> None:
    n = 70
    targets = targets_consumer(consumer_frame, n)
    res = draw_cells(consumer_frame, n, targets, np.random.default_rng(3))
    units = expand_units(consumer_frame, res.counts)
    totale = float(consumer_frame["count"].sum())
    w = rake_weights(units, targets, totale)
    assert w.weight.sum() == pytest.approx(n)
    assert w.weight_pop.sum() == pytest.approx(totale)
    assert (w.weight > 0).all()
    assert w.warnings == []
    units = units.with_columns(pl.Series("weight", w.weight))
    for t in targets:
        agg = units.group_by(t.variable).agg(pl.col("weight").sum())
        got = dict(zip(agg[t.variable].to_list(), (agg["weight"] / n).to_list(), strict=True))
        for c, share in t.population_shares.items():
            assert got.get(c, 0.0) == pytest.approx(share, abs=1e-8)


def test_pesi_con_categoria_assente() -> None:
    units = pl.DataFrame({"x": ["a", "a", "b"], "y": ["p", "q", "p"]})
    targets = [
        q.QuotaTarget(
            "x",
            {"a": 0.5, "b": 0.3, "c": 0.2},
            {"a": 0.5, "b": 0.3, "c": 0.2},
            {"a": 2, "b": 1, "c": 0},
            False,
        ),
        q.QuotaTarget("y", {"p": 0.6, "q": 0.4}, {"p": 0.6, "q": 0.4}, {"p": 2, "q": 1}, False),
    ]
    w = rake_weights(units, targets, 1000.0)
    assert any("nessuna unità per c" in a for a in w.warnings)
    assert w.weight.sum() == pytest.approx(3)
    # Le quote attive vengono rinormalizzate: a e b nel rapporto 5:3.
    wa = w.weight[0] + w.weight[1]
    wb = w.weight[2]
    assert wa / wb == pytest.approx(5 / 3, rel=1e-6)


def test_pesi_segnalano_incompatibilita() -> None:
    """Target che il campione non può soddisfare: la variabile non sovracampionata viene esclusa."""
    units = pl.DataFrame({"x": ["a", "a", "b", "b"], "y": ["p", "p", "q", "q"]})
    targets = [
        q.QuotaTarget("x", {"a": 0.9, "b": 0.1}, {"a": 0.5, "b": 0.5}, {"a": 2, "b": 2}, True),
        q.QuotaTarget("y", {"p": 0.3, "q": 0.7}, {"p": 0.5, "q": 0.5}, {"p": 2, "q": 2}, False),
    ]
    w = rake_weights(units, targets, 100.0)
    assert any("calibrati senza y" in a for a in w.warnings)
    # x (sovracampionata) resta ricostruita: a pesa 0.9.
    assert (w.weight[:2].sum() / w.weight.sum()) == pytest.approx(0.9, abs=1e-8)
