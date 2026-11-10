"""CLI `run` e `freeze` con il provider finto."""

from pathlib import Path

from typer.testing import CliRunner

from survey_simulator.cli import app
from survey_simulator.runner import read_manifest
from tests.test_cli_interview import _config_finta

runner = CliRunner()


def test_run_pilota_e_freeze(tmp_path: Path) -> None:
    cfg = _config_finta(tmp_path)
    stima = runner.invoke(app, ["run", "-c", str(cfg), "--pilot", "--estimate-only"])
    assert stima.exit_code == 0, stima.output
    assert "Piano: 108 interviste" in stima.output and "nessuna chiamata" in stima.output
    assert not (tmp_path / "runs").exists()

    result = runner.invoke(app, ["run", "-c", str(cfg), "--pilot", "--run-id", "pilota"])
    assert result.exit_code == 0, result.output
    assert "Interviste fatte 108, saltate 0" in result.output
    assert "non congelato" in result.output
    run_dir = tmp_path / "runs" / "pilota"
    assert (run_dir / "responses_long.csv").is_file()

    gelo = runner.invoke(app, ["freeze", str(run_dir)])
    assert gelo.exit_code == 0 and "Run congelato" in gelo.output
    m = read_manifest(run_dir)
    assert m is not None and m["frozen"] is True
    di_nuovo = runner.invoke(app, ["freeze", str(run_dir)])
    assert di_nuovo.exit_code == 0 and "già congelato" in di_nuovo.output
    verifica = runner.invoke(app, ["freeze", str(run_dir), "--verify"])
    assert verifica.exit_code == 0 and "integro" in verifica.output

    ancora = runner.invoke(app, ["run", "-c", str(cfg), "--pilot", "--run-id", "pilota"])
    assert ancora.exit_code == 4 and "congelato" in ancora.output

    (run_dir / "interviews.json").write_text("[]", encoding="utf-8")
    rotto = runner.invoke(app, ["freeze", str(run_dir), "--verify"])
    assert rotto.exit_code == 1 and "file modificato: interviews.json" in rotto.output


def test_freeze_senza_manifest(tmp_path: Path) -> None:
    result = runner.invoke(app, ["freeze", str(tmp_path)])
    assert result.exit_code == 1 and "manifest assente" in result.output
