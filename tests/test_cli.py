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


def test_data_status_sul_repo() -> None:
    from pathlib import Path

    data_dir = Path(__file__).resolve().parents[1] / "data"
    result = runner.invoke(app, ["data", "status", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, result.output
    assert "Hash verificati" in result.output
    assert "firms_region_sector_size" in result.output


def test_data_status_senza_manifest(tmp_path) -> None:
    result = runner.invoke(app, ["data", "status", "--data-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "Nessun manifest" in result.output


def test_data_fetch_offline_senza_cache(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "data",
            "fetch",
            "--offline",
            "--data-dir",
            str(tmp_path),
            "--table",
            "firms_region_sector_size",
        ],
    )
    assert result.exit_code == 1
    assert "offline" in result.output


def test_data_fetch_tavola_sconosciuta(tmp_path) -> None:
    result = runner.invoke(app, ["data", "fetch", "--data-dir", str(tmp_path), "--table", "nope"])
    assert result.exit_code == 2
    assert "Tavole sconosciute" in result.output


def test_data_fetch_offline_con_cache(tmp_path, monkeypatch) -> None:
    """Percorso riuscito di `data fetch --offline`: cache precaricata dalle fixture."""
    import dataclasses
    import functools

    import httpx

    import synthsurvey.population.istat as istat
    from tests.population.conftest import REGIONI_FIXTURE, dataflow_from_url, fixture_text

    nome = "firms_region_sector_size"
    spec = istat.TABLES[nome]
    # Normalizzazione limitata alle regioni presenti nelle fixture.
    monkeypatch.setitem(
        istat.TABLES,
        nome,
        dataclasses.replace(
            spec, normalize=functools.partial(spec.normalize, required_regions=REGIONI_FIXTURE)
        ),
    )
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, text=fixture_text(dataflow_from_url(str(r.url))))
    )
    client = istat.SdmxClient(tmp_path / "raw", transport=transport)
    for req in spec.requests:
        client.fetch_csv(req.dataflow, req.key, req.start, req.end)

    result = runner.invoke(
        app, ["data", "fetch", "--offline", "--data-dir", str(tmp_path), "--table", nome]
    )
    assert result.exit_code == 0, result.output
    assert "sorgente da cache" in result.output
    assert (tmp_path / "processed" / f"{nome}.csv").is_file()

    status = runner.invoke(app, ["data", "status", "--data-dir", str(tmp_path)])
    assert status.exit_code == 0, status.output
    assert "Hash verificati" in status.output
