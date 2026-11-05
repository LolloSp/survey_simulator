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
    """`python -m synthsurvey` deve funzionare (workaround per Smart App Control)."""
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
