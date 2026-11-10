"""CLI `interview preview` in CATI e CAPI con il provider finto: le stesse 10 persone (M8)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from survey_simulator.cli import app
from tests.test_cli_interview import _config_finta

runner = CliRunner()


def test_interview_preview_cati_e_capi(tmp_path: Path) -> None:
    cfg = _config_finta(tmp_path)
    persone: dict[str, set[str]] = {}
    for mode in ("cati", "capi"):
        out = tmp_path / mode
        result = runner.invoke(
            app,
            [
                "interview",
                "preview",
                "-c",
                str(cfg),
                "--mode",
                mode,
                "--n",
                "10",
                "--out",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert f"Interviste {mode.upper()}: 10 persone, 10 completate" in result.output
        righe = json.loads((out / "responses.json").read_text(encoding="utf-8"))
        persone[mode] = {r["persona_id"] for r in righe}
        assert all(r["mode"] == mode for r in righe)
        emessi = [r for r in righe if r["nonverbal_emitted"] is not None]
        assert emessi, "segnali non verbali registrati"
        osservati = [r["nonverbal_observed"] for r in emessi]
        if mode == "cati":
            assert all("body" not in o for o in osservati)
        else:
            assert all("body" in o for o in osservati)
        trascrizione = next((out / "transcripts").glob("*.md")).read_text(encoding="utf-8")
        assert "**intervistatore**" in trascrizione and "**rispondente**" in trascrizione
    assert persone["cati"] == persone["capi"] and len(persone["cati"]) == 10
