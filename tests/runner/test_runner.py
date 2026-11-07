"""Runner: piano, stima, esecuzione con client finto, output, manifest, congelamento."""

import json
import time
from pathlib import Path
from typing import Any

import polars as pl
import pytest
import yaml

from synthsurvey.config import LoadedConfig, load_config
from synthsurvey.llm import FakeLLMClient, LLMPool, default_pricing
from synthsurvey.population.tables import IstatTables, load_tables
from synthsurvey.questionnaire import Mode
from synthsurvey.runner import (
    BudgetError,
    FrozenError,
    assign_modes,
    build_plan,
    estimate_cost,
    execute_run,
    freeze_run,
    is_frozen,
    prepare,
    read_manifest,
    verify_frozen,
    write_manifest,
)
from synthsurvey.runner import plan as plan_module
from tests.config.conftest import ESEMPI_DIR
from tests.interview.conftest import make_persona

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
QUESTIONARIO = ESEMPI_DIR.parent.parent / "questionnaires" / "examples" / "mercato_v1.yaml"


@pytest.fixture(scope="session")
def tables() -> IstatTables:
    return load_tables(PROCESSED)


def config_finta(tmp_path: Path, **engine: Any) -> LoadedConfig:
    raw = yaml.safe_load((ESEMPI_DIR / "mercato_100.yaml").read_text(encoding="utf-8"))
    raw["engine"]["models"] = [{"provider": "fake", "model": "fake-1"}]
    raw["engine"].update(engine)
    raw["questionnaire"]["path"] = str(QUESTIONARIO)
    raw["output"]["dir"] = str(tmp_path / "runs")
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return load_config(path)


def test_piano_within_e_between(tmp_path: Path) -> None:
    loaded = config_finta(tmp_path, replicates=2)
    persone = [make_persona(f"p_{i:05d}") for i in range(5)]
    piano = build_plan(loaded.config, persone)
    assert len(piano) == 5 * 3 * 2 and len({p.key for p in piano}) == len(piano)
    assert {p.mode for p in piano} == set(Mode)
    raw = yaml.safe_load(loaded.path.read_text(encoding="utf-8"))
    raw["modes"] = {
        "design": "between_subject",
        "enabled": ["cawi", "cati", "capi"],
        "allocation": {"cawi": 0.5, "cati": 0.3, "capi": 0.2},
    }
    loaded.path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    cfg = load_config(loaded.path).config
    persone = [make_persona(f"p_{i:05d}") for i in range(10)]
    modi = assign_modes(cfg, 10)
    assert sorted(m.value for m in modi) == ["capi"] * 2 + ["cati"] * 3 + ["cawi"] * 5
    assert modi == assign_modes(cfg, 10), "riproducibile dal seed"
    piano = build_plan(cfg, persone)
    assert len(piano) == 10 * 2
    per_persona = {
        p.persona_id: {q.mode for q in piano if q.persona_id == p.persona_id} for p in persone
    }
    assert all(len(v) == 1 for v in per_persona.values())


def test_stima_costi_e_budget(tmp_path: Path, tables: IstatTables) -> None:
    loaded = config_finta(tmp_path)
    persone, _q, mqs, _ = prepare(loaded, data_dir=PROCESSED.parent, pilot=True, tables=tables)
    piano = build_plan(loaded.config, persone)
    stima = estimate_cost(loaded.config, piano, persone, mqs, default_pricing(0.92))
    assert stima.interviews == 12 * 3 * 3 and stima.calls > stima.interviews
    assert stima.cost_usd == 0.0 and stima.within_budget, "il modello finto è gratis"
    caro = config_finta(tmp_path, models=[{"provider": "anthropic", "model": "claude-opus-5-5"}])
    stima_cara = estimate_cost(caro.config, piano, persone, mqs, default_pricing(0.92))
    assert stima_cara.cost_eur > 0 and stima_cara.by_model["claude-opus-5-5"] > 0
    assert stima_cara.input_tokens > stima_cara.output_tokens
    raw = yaml.safe_load(caro.path.read_text(encoding="utf-8"))
    raw["run"]["budget_max_eur"] = 0.01
    caro.path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(BudgetError, match="oltre il budget"):
        execute_run(load_config(caro.path), data_dir=PROCESSED.parent, pilot=True, tables=tables)
    assert not (tmp_path / "runs").exists(), "nessuna cartella scritta prima della stima"


def test_run_pilota_scrive_tutto_e_riparte_dalla_cache(tmp_path: Path, tables: IstatTables) -> None:
    loaded = config_finta(tmp_path)
    progressi: list[tuple[int, int]] = []
    result = execute_run(
        loaded,
        data_dir=PROCESSED.parent,
        pilot=True,
        run_id="pilota",
        tables=tables,
        progress=lambda f, t, s: progressi.append((f, t)),
    )
    run_dir = tmp_path / "runs" / "pilota"
    assert result.run_dir == run_dir and not result.budget_exceeded
    assert len(result.results) == 12 * 3 * 3 and progressi[-1] == (108, 108)
    for nome in (
        "manifest.json",
        "personas.parquet",
        "personas.csv",
        "personas.json",
        "responses_long.parquet",
        "responses_long.csv",
        "interviews.json",
    ):
        assert (run_dir / nome).is_file(), nome
    m = read_manifest(run_dir)
    assert m is not None and m["status"] == "completed" and m["frozen"] is False
    assert m["interviews_done"] == 108 and m["interviews_skipped"] == 0
    assert m["records"] == 108 * 12 and m["plan"]["design"] == "within_subject"
    assert m["questionnaire"]["sha256"] and m["prompts"]["respondent_it.j2"]
    assert m["config"]["project"]["seed"] == loaded.config.project.seed
    assert "fake/fake-1" in m["stats"] and m["stats"]["fake/fake-1"]["cache_hits"] == 0
    assert set(m["data_tables"]) and all(v["sha256"] for v in m["data_tables"].values())
    lungo = pl.read_parquet(run_dir / "responses_long.parquet")
    assert lungo.height == 108 * 12
    assert set(lungo["mode"].unique().to_list()) == {"cawi", "cati", "capi"}
    assert lungo["replicate"].max() == 3
    assert json.loads(lungo.filter(pl.col("mode") == "cati")["nonverbal_emitted"][0])
    trascrizioni = list((run_dir / "transcripts").glob("*.md"))
    assert len(trascrizioni) == 108
    esiti = json.loads((run_dir / "interviews.json").read_text(encoding="utf-8"))
    assert len(esiti) == 108 and all(e["completed"] for e in esiti)
    # Secondo avvio con lo stesso run_id: tutte le risposte vengono dalla cache.
    di_nuovo = execute_run(
        loaded, data_dir=PROCESSED.parent, pilot=True, run_id="pilota", tables=tables
    )
    stats = di_nuovo.manifest["stats"]["fake/fake-1"]
    assert stats["calls"] == 0 and stats["cache_hits"] > 0


def test_run_completo_100_per_3_modalita_per_3_repliche(
    tmp_path: Path, tables: IstatTables
) -> None:
    """Criterio di M9: un run da 100 x 3 x 3 completa e può essere congelato."""
    loaded = config_finta(tmp_path)
    pools = [LLMPool(FakeLLMClient("fake-1"), pricing=default_pricing(0.92), concurrency=8)]
    inizio = time.monotonic()
    result = execute_run(
        loaded, data_dir=PROCESSED.parent, run_id="completo", tables=tables, pools=pools
    )
    durata = time.monotonic() - inizio
    assert len(result.results) == 900, f"{durata:.1f} s"
    assert result.manifest["records"] == 900 * 12
    manifest = freeze_run(result.run_dir)
    assert manifest["frozen"] and len(manifest["files"]) == 900 + 6
    assert verify_frozen(result.run_dir) == []


def test_budget_superato_durante_il_run(
    tmp_path: Path, tables: IstatTables, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = config_finta(tmp_path, models=[{"provider": "anthropic", "model": "claude-haiku-5-5"}])
    raw = yaml.safe_load(loaded.path.read_text(encoding="utf-8"))
    raw["run"]["budget_max_eur"] = 0.002
    loaded.path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    loaded = load_config(loaded.path)
    # La stima viene forzata entro il budget: la spesa reale (finta ma prezzata) lo supera.
    vera = plan_module.CostEstimate
    monkeypatch.setattr(
        "synthsurvey.runner.run.estimate_cost",
        lambda *a, **k: vera(1, 1, 1, 1, 0.0, 0.0, 0.002, {}),
    )
    pools = [LLMPool(FakeLLMClient("claude-haiku-5-5"), pricing=default_pricing(0.92))]
    result = execute_run(
        loaded, data_dir=PROCESSED.parent, pilot=True, run_id="budget", tables=tables, pools=pools
    )
    assert result.budget_exceeded and result.skipped > 0 and result.results
    assert result.manifest["status"] == "budget_exceeded" and result.cost_eur > 0.002


def test_congelamento(tmp_path: Path, tables: IstatTables) -> None:
    loaded = config_finta(tmp_path, replicates=1)
    result = execute_run(
        loaded, data_dir=PROCESSED.parent, pilot=True, run_id="gelo", tables=tables
    )
    run_dir = result.run_dir
    assert not is_frozen(run_dir)
    manifest = freeze_run(run_dir)
    assert is_frozen(run_dir) and manifest["frozen_at"] and "manifest.json" not in manifest["files"]
    assert freeze_run(run_dir) == manifest, "idempotente"
    assert verify_frozen(run_dir) == []
    with pytest.raises(FrozenError):
        write_manifest(run_dir, {"x": 1})
    with pytest.raises(FrozenError):
        execute_run(loaded, data_dir=PROCESSED.parent, pilot=True, run_id="gelo", tables=tables)
    (run_dir / "interviews.json").write_text("[]", encoding="utf-8")
    (run_dir / "nuovo.txt").write_text("x", encoding="utf-8")
    problemi = verify_frozen(run_dir)
    assert "file modificato: interviews.json" in problemi and "file aggiunto: nuovo.txt" in problemi
    assert verify_frozen(tmp_path) == ["il run non è congelato"]


def test_config_frozen_congela_subito(tmp_path: Path, tables: IstatTables) -> None:
    loaded = config_finta(tmp_path, replicates=1)
    raw = yaml.safe_load(loaded.path.read_text(encoding="utf-8"))
    raw["run"]["frozen"] = True
    raw["modes"]["enabled"] = ["cawi"]
    loaded.path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    result = execute_run(
        load_config(loaded.path),
        data_dir=PROCESSED.parent,
        pilot=True,
        run_id="auto",
        tables=tables,
    )
    assert result.manifest["frozen"] is True and is_frozen(result.run_dir)
    assert len(result.results) == 12
