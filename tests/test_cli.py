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


def test_llm_prices() -> None:
    result = runner.invoke(app, ["llm", "prices"])
    assert result.exit_code == 0, result.output
    assert "claude-opus-5-5" in result.output and "USD/MTok" in result.output


def test_llm_ping_con_provider_finto(tmp_path) -> None:
    import yaml

    from tests.config.conftest import config_base

    raw = config_base()
    raw["engine"]["models"] = [{"provider": "fake", "model": "fake-1"}]
    (tmp_path / "questionario.yaml").write_text("id: q\nsections: []\n", encoding="utf-8")
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    result = runner.invoke(app, ["llm", "ping", "--config", str(path)])
    assert result.exit_code == 0, result.output
    assert "Provider fake" in result.output and "costo 0.00000 USD" in result.output
    fuori = runner.invoke(app, ["llm", "ping", "--config", str(path), "--model-index", "3"])
    assert fuori.exit_code == 2


def _config_finta(tmp_path, responder=None, monkeypatch=None):
    import yaml

    from tests.config.conftest import config_base

    raw = config_base()
    raw["engine"]["models"] = [{"provider": "fake", "model": "fake-1"}]
    raw["output"]["dir"] = str(tmp_path / "runs")
    (tmp_path / "questionario.yaml").write_text("id: q\nsections: []\n", encoding="utf-8")
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    if responder is not None and monkeypatch is not None:
        from synthsurvey.llm import FakeLLMClient, registry

        monkeypatch.setattr(
            registry, "make_client", lambda spec, cfg: FakeLLMClient(spec.model, responder)
        )
    return path


def test_questionnaire_import_valido(tmp_path, monkeypatch) -> None:
    import yaml

    from tests.questionnaire.draft_example import bozza

    cfg = _config_finta(tmp_path, lambda r: bozza(), monkeypatch)
    sorgente = tmp_path / "grezzo.txt"
    sorgente.write_text("D1. Quanto soddisfatto? scala 1-10\n", encoding="utf-8")
    out = tmp_path / "out" / "energia.yaml"
    result = runner.invoke(
        app, ["questionnaire", "import", str(sorgente), "--config", str(cfg), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert "YAML valido" in result.output and "8 domande" in result.output
    assert out.is_file() and (tmp_path / "out" / "energia.import.md").is_file()
    assert yaml.safe_load(out.read_text(encoding="utf-8"))["id"] == "energia_2026"
    # Lo YAML prodotto passa `questionnaire validate` con la stessa config.
    valid = runner.invoke(app, ["questionnaire", "validate", str(out), "--config", str(cfg)])
    assert valid.exit_code == 0, valid.output


def test_questionnaire_import_bozza_non_valida(tmp_path, monkeypatch) -> None:
    from tests.questionnaire.draft_example import bozza_rotta

    cfg = _config_finta(tmp_path, lambda r: bozza_rotta(), monkeypatch)
    sorgente = tmp_path / "grezzo.md"
    sorgente.write_text("D1. Domanda\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["questionnaire", "import", str(sorgente), "--config", str(cfg), "--rounds", "0"],
    )
    assert result.exit_code == 2, result.output
    assert "NON valida" in result.output and "1 errori" in result.output
    assert (tmp_path / "grezzo.draft.yaml").is_file()
    assert (tmp_path / "grezzo.draft.import.md").is_file()


def test_questionnaire_import_senza_bozza(tmp_path) -> None:
    # Il client finto di default riempie lo schema con segnaposto non conformi alla bozza.
    cfg = _config_finta(tmp_path)
    sorgente = tmp_path / "grezzo.md"
    sorgente.write_text("D1. Domanda\n", encoding="utf-8")
    result = runner.invoke(
        app, ["questionnaire", "import", str(sorgente), "-c", str(cfg), "--rounds", "1"]
    )
    assert result.exit_code == 2, result.output
    assert "Nessuna bozza prodotta" in result.output and "Giri 2" in result.output
    assert not (tmp_path / "grezzo.draft.yaml").exists()
    assert (tmp_path / "grezzo.import.md").is_file()


def test_questionnaire_import_errori_di_input(tmp_path) -> None:
    cfg = _config_finta(tmp_path)
    manca = runner.invoke(
        app, ["questionnaire", "import", str(tmp_path / "x.docx"), "-c", str(cfg)]
    )
    assert manca.exit_code == 1 and "Errore di estrazione" in manca.output
    sorgente = tmp_path / "g.txt"
    sorgente.write_text("D1.\n", encoding="utf-8")
    effort = runner.invoke(
        app, ["questionnaire", "import", str(sorgente), "-c", str(cfg), "--effort", "max"]
    )
    assert effort.exit_code == 2 and "--effort" in effort.output
    idx = runner.invoke(
        app, ["questionnaire", "import", str(sorgente), "-c", str(cfg), "--model-index", "5"]
    )
    assert idx.exit_code == 2
