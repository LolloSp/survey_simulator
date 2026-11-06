"""Campione completo sulle config di esempio: dimensioni, quote, pesi, determinismo, CLI."""

import copy
import json
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from synthsurvey.cli import app
from synthsurvey.config import load_config, parse_config
from synthsurvey.population.individui import age_group_of
from synthsurvey.population.istat.codelists import age_band
from synthsurvey.population.sample import UNIT_COLUMNS, SampleResult, build_sample
from synthsurvey.population.tables import IstatTables, load_tables
from tests.config.conftest import ESEMPI_DIR, config_base

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
DATA_DIR = PROCESSED.parent


@pytest.fixture(scope="module")
def tables() -> IstatTables:
    return load_tables(PROCESSED)


def campione(nome: str, tables: IstatTables, **kw: object) -> SampleResult:
    cfg = load_config(ESEMPI_DIR / f"{nome}.yaml").config
    return build_sample(cfg, PROCESSED, tables=tables, **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize("nome", ["mercato_100", "mercato_500", "mercato_1000"])
def test_esempi_rispettano_quote_e_pesi(nome: str, tables: IstatTables) -> None:
    res = campione(nome, tables)
    cfg = load_config(ESEMPI_DIR / f"{nome}.yaml").config
    assert res.units.height == cfg.sample.total
    assert res.units.columns == UNIT_COLUMNS
    assert res.units["unit_id"].n_unique() == res.units.height
    for seg in res.segments.values():
        assert seg.units.height == seg.n
        assert seg.draw.max_deviation == 0, seg.name
        for t in seg.targets:
            assert seg.draw.achieved[t.variable] == t.targets
            # Pesi: distribuzione pesata uguale alla popolazione, salvo incompatibilità dichiarata.
            if any("calibrati senza " + t.variable in w for w in seg.warnings):
                continue
            agg = seg.units.group_by(t.variable).agg(pl.col("weight").sum())
            got = dict(
                zip(agg[t.variable].to_list(), (agg["weight"] / seg.n).to_list(), strict=True)
            )
            for c, share in t.population_shares.items():
                assert got.get(c, 0.0) == pytest.approx(share, abs=1e-6), (seg.name, t.variable, c)
        assert seg.weights.weight.sum() == pytest.approx(seg.n)
        assert seg.weights.weight_pop.sum() == pytest.approx(seg.population_total)


def test_pesi_esatti_senza_incompatibilita_sui_campioni_grandi(tables: IstatTables) -> None:
    for nome in ("mercato_500", "mercato_1000"):
        res = campione(nome, tables)
        assert not any("calibrati senza" in w for w in res.warnings), res.warnings


def test_attributi_per_segmento(tables: IstatTables) -> None:
    res = campione("mercato_500", tables)
    consumer = res.units.filter(pl.col("segment") == "consumer")
    pmi = res.units.filter(pl.col("segment") == "pmi")
    assert consumer["sector"].is_null().all() and consumer["size_class"].is_null().all()
    assert pmi["sex"].is_null().all() and pmi["age"].is_null().all()
    # Filtri della config 500: età 18-80, solo nord e centro, tre settori.
    assert consumer["age"].min() >= 18 and consumer["age"].max() <= 80
    assert set(consumer["macro_area"].unique().to_list()) <= {"nord_ovest", "nord_est", "centro"}
    assert set(pmi["sector"].unique().to_list()) <= {"industria", "commercio", "servizi_imprese"}
    assert set(pmi["size_class"].unique().to_list()) == {"micro", "piccola", "media"}
    # Fascia d'età coerente con l'età puntuale.
    for eta, fascia in zip(consumer["age"].to_list(), consumer["age_band"].to_list(), strict=True):
        assert age_band(eta) == fascia
        age_group_of(eta)


def test_determinismo_del_seed(tables: IstatTables) -> None:
    a = campione("mercato_100", tables)
    b = campione("mercato_100", tables)
    assert a.units.equals(b.units)
    base = load_config(ESEMPI_DIR / "mercato_100.yaml").config
    altro = base.model_copy(update={"project": base.project.model_copy(update={"seed": 99})})
    c = build_sample(altro, PROCESSED, tables=tables)
    assert not a.units.drop("weight", "weight_pop").equals(c.units.drop("weight", "weight_pop"))


def test_pilota(tables: IstatTables) -> None:
    res = campione("mercato_100", tables, n_total=12)
    assert res.units.height == 12
    assert {k: v.n for k, v in res.segments.items()} == {"consumer": 8, "pmi": 4}


def test_allocazione_proporzionale(tables: IstatTables) -> None:
    raw = copy.deepcopy(config_base())
    raw["sample"]["allocation"] = "proportional"
    for seg in raw["sample"]["segments"].values():
        del seg["share"]
    cfg = parse_config(raw)
    res = build_sample(cfg, PROCESSED, tables=tables)
    sizes = {k: v.n for k, v in res.segments.items()}
    assert sum(sizes.values()) == 100
    assert sizes["consumer"] > 85, "50 milioni di adulti contro 4,7 milioni di imprese"


def test_avvisi_celle_piccole_nel_risultato(tables: IstatTables) -> None:
    res = campione("mercato_100", tables)
    assert any("casi attesi sotto 3" in w for w in res.warnings)


def test_cli_sample_preview(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "sample",
            "preview",
            "--config",
            str(ESEMPI_DIR / "mercato_100.yaml"),
            "--data-dir",
            str(DATA_DIR),
            "--out",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "100 unità" in result.output
    assert "size_class (sovracampionata)" in result.output
    csv = pl.read_csv(tmp_path / "sample.csv")
    assert csv.height == 100
    diag = json.loads((tmp_path / "sample_diagnostics.json").read_text(encoding="utf-8"))
    assert diag["segments"]["pmi"]["quotas"]["size_class"]["oversampled"] is True
    assert diag["segments"]["consumer"]["max_deviation"] == 0

    pilota = runner.invoke(
        app,
        [
            "sample",
            "preview",
            "--config",
            str(ESEMPI_DIR / "mercato_100.yaml"),
            "--data-dir",
            str(DATA_DIR),
            "--pilot",
        ],
    )
    assert pilota.exit_code == 0, pilota.output
    assert "12 unità [pilota]" in pilota.output


def test_cli_sample_preview_senza_dati(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "sample",
            "preview",
            "--config",
            str(ESEMPI_DIR / "mercato_100.yaml"),
            "--data-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "manifest" in result.output
