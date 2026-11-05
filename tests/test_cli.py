"""Test dello scheletro della CLI (M0)."""

import pytest
from typer.testing import CliRunner

from synthsurvey import __version__
from synthsurvey.cli import app

runner = CliRunner()


def test_help_funziona() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "synthsurvey" in result.output
    for comando in ("data", "sample", "run", "freeze", "report", "validate"):
        assert comando in result.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["data", "fetch"],
        ["sample", "preview"],
        ["run"],
        ["run", "--pilot"],
        ["freeze", "runs/x"],
        ["report", "runs/x"],
        ["validate", "runs/x", "--real", "reali.csv"],
    ],
)
def test_comandi_non_implementati_escono_con_1(args: list[str]) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert "non ancora implementato" in result.output


def test_modulo_eseguibile() -> None:
    """`python -m synthsurvey` deve essere equivalente al comando `synthsurvey`."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "synthsurvey", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout


def test_config_validate_ok() -> None:
    from pathlib import Path

    esempio = Path(__file__).resolve().parents[1] / "configs" / "examples" / "mercato_100.yaml"
    result = runner.invoke(app, ["config", "validate", str(esempio)])
    assert result.exit_code == 0, result.output
    assert "Configurazione valida" in result.output
    assert "consumer=70, pmi=30" in result.output
    assert "Interviste previste: 900" in result.output


def test_config_validate_errore(tmp_path) -> None:
    rotta = tmp_path / "rotta.yaml"
    rotta.write_text("project: {name: x, seed: 1}\n", encoding="utf-8")
    result = runner.invoke(app, ["config", "validate", str(rotta)])
    assert result.exit_code == 1
    assert "Configurazione non valida" in result.output
