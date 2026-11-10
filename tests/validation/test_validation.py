"""Validazione M11: import dei dati reali, allineamento, metriche, rapporto, CLI."""

import json
from pathlib import Path

import polars as pl
import pytest
import yaml
from typer.testing import CliRunner

from survey_simulator.cli import app
from survey_simulator.config import load_config
from survey_simulator.llm import FakeLLMClient, LLMPool, default_pricing
from survey_simulator.output import build_wide, load_run
from survey_simulator.personas.build import personas_frame
from survey_simulator.population.tables import load_tables
from survey_simulator.runner import FrozenError, execute_run, freeze_run
from survey_simulator.validation import (
    RealDataError,
    align,
    js_divergence,
    load_real,
    mean_ci,
    pearson,
    share_ci,
    total_variation,
    validate_frames,
    validate_run,
)
from tests.config.conftest import ESEMPI_DIR

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
QUESTIONARIO = ESEMPI_DIR.parent.parent / "questionnaires" / "examples" / "mercato_v1.yaml"
runner = CliRunner()


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("run")
    raw = yaml.safe_load((ESEMPI_DIR / "mercato_100.yaml").read_text(encoding="utf-8"))
    raw["engine"]["models"] = [{"provider": "fake", "model": "fake-1"}]
    raw["engine"]["replicates"] = 1
    raw["questionnaire"]["path"] = str(QUESTIONARIO)
    raw["output"]["dir"] = str(tmp / "runs")
    path = tmp / "config.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    pools = [LLMPool(FakeLLMClient("fake-1"), pricing=default_pricing(0.92))]
    return execute_run(
        load_config(path),
        data_dir=PROCESSED.parent,
        pilot=True,
        run_id="pilota",
        tables=load_tables(PROCESSED),
        pools=pools,
    ).run_dir


@pytest.fixture(scope="module")
def reali(run_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Dati "reali" fittizi derivati dal simulato: CAWI e CATI, con un po' di rumore."""
    _m, long, personas, q = load_run(run_dir)
    wide, _v = build_wide(long, personas_frame(personas), q)
    sub = wide.filter(pl.col("mode").is_in(["cawi", "cati"])).rename(
        {"persona_id": "respondent_id"}
    )
    # Rumore: un terzo dei rispondenti dà 3 alla q1 e sceglie l'opzione 2 alla q3.
    idx = pl.int_range(0, sub.height, eager=True) % 3 == 0
    sub = sub.with_columns(
        pl.when(idx).then(3).otherwise(pl.col("q1")).alias("q1"),
        pl.when(idx).then(2).otherwise(pl.col("q3")).alias("q3"),
    )
    cartella = tmp_path_factory.mktemp("reali")
    largo = cartella / "reali_largo.csv"
    sub.select(
        ["respondent_id", "mode", "segment", "weight"]
        + [c for c in sub.columns if c.startswith("q") and not c.endswith("_status") and c != "q7"]
    ).write_csv(largo)
    lungo_df = long.filter(
        pl.col("mode").is_in(["cawi", "cati"]) & (pl.col("status") != "not_applicable")
    ).select(
        pl.col("persona_id").alias("respondent_id"),
        "mode",
        "question_id",
        "item_id",
        "answer_code",
        "segment",
    )
    lungo = cartella / "reali_lungo.csv"
    lungo_df.write_csv(lungo)
    return {"largo": largo, "lungo": lungo, "cartella": cartella}


def test_metriche_di_base() -> None:
    assert js_divergence({1: 0.5, 2: 0.5}, {1: 0.5, 2: 0.5}) == 0.0
    assert js_divergence({1: 1.0}, {2: 1.0}) == pytest.approx(1.0)
    assert js_divergence({}, {1: 1.0}) is None
    assert total_variation({1: 0.7, 2: 0.3}, {1: 0.4, 2: 0.6}) == pytest.approx(0.3)
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert pearson([1, 1, 1], [1, 2, 3]) is None and pearson([1, 2], [1, 2]) is None
    lo, hi = share_ci(0.5, 100)
    assert lo == pytest.approx(0.402, abs=0.001) and hi == pytest.approx(0.598, abs=0.001)
    assert share_ci(0.5, 0) == (0.0, 1.0)
    lo, hi = mean_ci(5.0, 2.0, 100)
    assert lo == pytest.approx(4.608, abs=0.001) and hi == pytest.approx(5.392, abs=0.001)
    assert mean_ci(5.0, None, 10) == (5.0, 5.0)


def test_import_lungo_e_largo_coincidono(run_dir: Path, reali: dict[str, Path]) -> None:
    _m, _long, _p, q = load_run(run_dir)
    largo = load_real(reali["largo"], q)
    lungo = load_real(reali["lungo"], q)
    assert largo.height == lungo.height == 24, "12 persone x 2 modalità"
    assert set(largo["mode"].unique().to_list()) == {"cawi", "cati"}
    chiavi = ["respondent_id", "mode"]
    a = largo.sort(chiavi).select([*chiavi, "q4_1", "q5_a", "q6", "q8"])
    b = lungo.sort(chiavi).select([*chiavi, "q4_1", "q5_a", "q6", "q8"])
    assert a.equals(b), "stessa codifica dai due formati"
    assert lungo.filter(pl.col("segment") == "consumer")["q8"].unique().to_list() == [-1]
    assert "weight" in lungo.columns and lungo["weight"].min() == 1.0
    assert largo["weight"].max() > 0


def test_import_errori(run_dir: Path, tmp_path: Path) -> None:
    _m, _long, _p, q = load_run(run_dir)
    with pytest.raises(RealDataError, match="non trovato"):
        load_real(tmp_path / "manca.csv", q)
    rotto = tmp_path / "rotto.csv"
    rotto.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(RealDataError, match="colonne non riconosciute"):
        load_real(rotto, q)


def test_allineamento_e_metriche(run_dir: Path, reali: dict[str, Path]) -> None:
    _m, long, personas, q = load_run(run_dir)
    wide, variables = build_wide(long, personas_frame(personas), q)
    real = load_real(reali["largo"], q)
    a = align(wide, real, variables)
    assert a.modes == ["cawi", "cati"] and a.simulated_only_modes == ["capi"]
    assert a.real_only_modes == [] and "q1" in a.variables and "segment" in a.subgroup_columns
    assert a.n_real == 24 and a.n_simulated == 36 and a.warnings == []
    result = validate_frames(wide, real, variables)
    per_nome = {c.name: c for c in result.comparisons}
    q1 = per_nome["q1"]
    assert q1.metric == "media" and q1.simulated == 1.0 and q1.real > 1.0
    assert q1.js is not None and q1.js > 0 and q1.tv == pytest.approx(1 / 3, abs=0.05)
    assert q1.within_ci is False, "il simulato è fuori dall'IC del reale rumoroso"
    q3 = per_nome["q3"]
    assert q3.metric == "quota" and q3.top_code == 1 and q3.real == pytest.approx(2 / 3, abs=0.05)
    q2 = per_nome["q2"]
    assert q2.js == 0.0 and q2.within_ci is True, "nessun rumore su q2"
    s = result.summary
    assert s["variables"] == len(a.variables) and 0 < s["within_ci_share"] < 1
    assert any(g["by"] == "segment" for g in result.subgroups)
    assert result.mode_effects["modes"] == ["cawi", "cati"]
    assert result.mode_effects["sign_agreement"] is not None
    # Reale identico al simulato: distanze nulle, tutto dentro l'IC.
    copia = wide.filter(pl.col("mode").is_in(["cawi", "cati"])).rename(
        {"persona_id": "respondent_id"}
    )
    identico = validate_frames(wide, copia, variables)
    assert all(c.js in (None, 0.0) for c in identico.comparisons)
    assert all(c.within_ci for c in identico.comparisons if c.within_ci is not None)
    assert identico.summary["js_mean"] == 0.0


def test_validate_run_scrive_rapporto_e_cli(
    run_dir: Path, reali: dict[str, Path], tmp_path: Path
) -> None:
    result, files = validate_run(run_dir, reali["largo"])
    assert [f.name for f in files] == ["validation.md", "validation.json"]
    assert files[0].parent == run_dir / "validation"
    md = files[0].read_text(encoding="utf-8")
    assert "# Validazione del run `pilota`" in md and "non validate" in md
    assert "solo nel simulato (non validate): capi" in md
    assert "| q1 | media |" in md and "## Sottogruppi" in md and "## Effetti di modalità" in md
    js = json.loads(files[1].read_text(encoding="utf-8"))
    assert js["summary"]["variables"] == result.summary["variables"]
    assert js["alignment"]["modes"] == ["cawi", "cati"]
    assert any(v["name"] == "q1" and v["diff"] < 0 for v in js["variables"])

    out = tmp_path / "val"
    cli = runner.invoke(
        app, ["validate", str(run_dir), "--real", str(reali["lungo"]), "--out", str(out)]
    )
    assert cli.exit_code == 0, cli.output
    assert "Modalità confrontate: cawi, cati" in cli.output and (out / "validation.md").is_file()
    manca = runner.invoke(app, ["validate", str(run_dir), "--real", str(tmp_path / "no.csv")])
    assert manca.exit_code == 1 and "non trovato" in manca.output

    freeze_run(run_dir)
    with pytest.raises(FrozenError):
        validate_run(run_dir, reali["largo"])
    gelo = runner.invoke(app, ["validate", str(run_dir), "--real", str(reali["largo"])])
    assert gelo.exit_code == 1 and "congelato" in gelo.output
    ok = runner.invoke(
        app,
        ["validate", str(run_dir), "--real", str(reali["largo"]), "--out", str(tmp_path / "v2")],
    )
    assert ok.exit_code == 0, ok.output
