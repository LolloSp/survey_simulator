"""Ensemble (M12): due modelli sulle stesse persone, divergenza nel report."""

from pathlib import Path
from typing import Any

import polars as pl
import yaml

from synthsurvey.config import load_config
from synthsurvey.llm import FakeLLMClient, LLMPool, LLMRequest, default_pricing, fill_schema
from synthsurvey.population.tables import load_tables
from synthsurvey.runner import execute_run
from tests.config.conftest import ESEMPI_DIR

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
QUESTIONARIO = ESEMPI_DIR.parent.parent / "questionnaires" / "examples" / "mercato_v1.yaml"


def _secondo_modello(r: LLMRequest) -> dict[str, Any]:
    """Un modello che alla q1 risponde sempre 9 e per il resto come il finto di default."""
    assert r.schema is not None
    out = fill_schema(r.schema)
    risposte = out.get("answers")
    if isinstance(risposte, dict) and "q1" in risposte:
        risposte["q1"] = 9
    if "answer" in out and r.messages[-1].content.startswith("Quanto è soddisfatto"):
        out["answer"] = 9
    return out


def test_ensemble_due_modelli(tmp_path: Path) -> None:
    raw = yaml.safe_load((ESEMPI_DIR / "mercato_100.yaml").read_text(encoding="utf-8"))
    raw["engine"]["models"] = [
        {"provider": "fake", "model": "fake-a"},
        {"provider": "fake", "model": "fake-b"},
    ]
    raw["engine"]["replicates"] = 1
    raw["modes"]["enabled"] = ["cawi", "cati"]
    raw["questionnaire"]["path"] = str(QUESTIONARIO)
    raw["output"]["dir"] = str(tmp_path / "runs")
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    pools = [
        LLMPool(FakeLLMClient("fake-a"), pricing=default_pricing(0.92)),
        LLMPool(FakeLLMClient("fake-b", _secondo_modello), pricing=default_pricing(0.92)),
    ]
    result = execute_run(
        load_config(path),
        data_dir=PROCESSED.parent,
        pilot=True,
        run_id="ensemble",
        tables=load_tables(PROCESSED),
        pools=pools,
    )
    assert len(result.results) == 12 * 2 * 2
    assert set(result.manifest["stats"]) == {"fake/fake-a", "fake/fake-b"}
    wide = pl.read_parquet(result.run_dir / "responses_wide.parquet")
    assert set(wide["model"].unique().to_list()) == {"fake-a", "fake-b"}
    assert wide.filter(pl.col("model") == "fake-a")["q1"].max() == 1
    assert wide.filter(pl.col("model") == "fake-b")["q1"].min() == 9
    html = (result.run_dir / "report.html").read_text(encoding="utf-8")
    assert "5b. Ensemble: divergenza fra modelli" in html
    assert '<th class="num">fake-a</th>' in html and '<th class="num">fake-b</th>' in html
    # q1 è la variabile più divergente e compare per prima nella tabella.
    inizio = html.index("5b. Ensemble")
    assert html.index("<td>q1</td>", inizio) < html.index("<td>q2</td>", inizio)
    assert "8.00" in html, "divergenza di 8 punti di scala su q1"
