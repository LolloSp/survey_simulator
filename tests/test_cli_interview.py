"""CLI `interview preview` con il provider finto: pilota CAWI da 10 persone (criterio M7)."""

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from survey_simulator.cli import app
from tests.config.conftest import ESEMPI_DIR

runner = CliRunner()


def _config_finta(tmp_path: Path) -> Path:
    raw = yaml.safe_load((ESEMPI_DIR / "mercato_100.yaml").read_text(encoding="utf-8"))
    raw["engine"]["models"] = [{"provider": "fake", "model": "fake-1"}]
    raw["questionnaire"]["path"] = str(
        ESEMPI_DIR.parent.parent / "questionnaires" / "examples" / "mercato_v1.yaml"
    )
    raw["output"]["dir"] = str(tmp_path / "runs")
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path


def test_interview_preview_cawi_pilota(tmp_path: Path) -> None:
    cfg = _config_finta(tmp_path)
    out = tmp_path / "pilota"
    result = runner.invoke(
        app,
        [
            "interview",
            "preview",
            "--config",
            str(cfg),
            "--mode",
            "cawi",
            "--n",
            "10",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Interviste CAWI: 10 persone, 10 completate" in result.output
    assert "costo 0.0000 USD" in result.output
    righe = json.loads((out / "responses.json").read_text(encoding="utf-8"))
    assert len({r["persona_id"] for r in righe}) == 10
    assert all(r["mode"] == "cawi" and r["replicate"] == 1 for r in righe)
    stati = {r["status"] for r in righe}
    assert "answered" in stati
    # Ogni persona ha un record per ogni domanda/item del questionario (12 chiavi).
    per_persona = {}
    for r in righe:
        per_persona.setdefault(r["persona_id"], set()).add((r["question_id"], r["item_id"]))
    assert all(len(v) == 12 for v in per_persona.values())
    assert (out / "responses.csv").is_file()
    trascrizioni = list((out / "transcripts").glob("*_cawi_r1.md"))
    assert len(trascrizioni) == 10


def test_interview_preview_errori(tmp_path: Path) -> None:
    cfg = _config_finta(tmp_path)
    modo = runner.invoke(app, ["interview", "preview", "-c", str(cfg), "--mode", "video"])
    assert modo.exit_code == 2 and "--mode" in modo.output
    idx = runner.invoke(app, ["interview", "preview", "-c", str(cfg), "--model-index", "4"])
    assert idx.exit_code == 2
