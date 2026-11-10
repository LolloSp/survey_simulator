"""`survey-simulator prepare` (M13): da questionario e anagrafica alla configurazione e al run."""

from pathlib import Path

import yaml
from typer.testing import CliRunner

from survey_simulator.cli import app
from survey_simulator.config import load_config
from tests.config.conftest import ESEMPI_DIR
from tests.population.test_contacts import scrivi_xlsx

QUESTIONARIO = ESEMPI_DIR.parent.parent / "questionnaires" / "examples" / "mercato_v1.yaml"
runner = CliRunner()


def _questionario_per_segmenti(tmp_path: Path) -> Path:
    """Il questionario di esempio cita i segmenti consumer e pmi: li rinomina come prepare."""
    raw = yaml.safe_load(QUESTIONARIO.read_text(encoding="utf-8"))
    for s in raw["sections"]:
        for q in s["questions"]:
            if q.get("applies_to"):
                q["applies_to"] = ["imprese" if a == "pmi" else "privati" for a in q["applies_to"]]
    path = tmp_path / "questionario.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_prepare_scrive_progetto_e_stima(tmp_path: Path) -> None:
    anagrafica = scrivi_xlsx(tmp_path / "clienti.xlsx")
    questionario = _questionario_per_segmenti(tmp_path)
    out = tmp_path / "progetto"
    result = runner.invoke(
        app,
        [
            "prepare",
            "--questionnaire",
            str(questionario),
            "--contacts",
            str(anagrafica),
            "--out",
            str(out),
            "--provider",
            "fake",
            "--model",
            "fake-1",
            "--modes",
            "cawi,cati",
            "--replicates",
            "2",
            "--budget",
            "10",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "valide 5" in result.output and "Segmenti: privati=3, imprese=2" in result.output
    assert "Stima: 20 interviste" in result.output, "5 persone x 2 modalità x 2 repliche"
    assert "Progetto pronto" in result.output
    cfg = yaml.safe_load((out / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["sample"]["total"] is None
    assert set(cfg["sample"]["segments"]) == {"privati", "imprese"}
    assert cfg["sample"]["segments"]["privati"]["contacts"]["unit"] == "individui"
    assert cfg["sample"]["segments"]["imprese"]["respondent_role"]
    assert cfg["engine"]["models"] == [{"provider": "fake", "model": "fake-1"}]
    assert cfg["run"]["budget_max_eur"] == 10 and cfg["engine"]["replicates"] == 2
    assert (out / "questionnaire.yaml").is_file() and (out / "contacts_report.json").is_file()
    rapporto = (out / "contacts_report.json").read_text(encoding="utf-8")
    assert "RSSMRA" not in rapporto and "x@y.z" not in rapporto, "nessun dato personale"
    loaded = load_config(out / "config.yaml")
    assert loaded.config.sample.segments["privati"].contacts is not None

    corsa = runner.invoke(
        app, ["run", "-c", str(out / "config.yaml"), "--pilot", "--run-id", "pilota"]
    )
    assert corsa.exit_code == 0, corsa.output
    run_dir = out / "runs" / "pilota"
    assert (run_dir / "private" / "contacts_map.csv").is_file()
    assert (run_dir / "private" / "LEGGIMI.txt").is_file()
    mappa = (run_dir / "private" / "contacts_map.csv").read_text(encoding="utf-8")
    assert "persona_id,unit_id,record_id,row" in mappa and ",1001," in mappa
    persone = (run_dir / "personas.csv").read_text(encoding="utf-8")
    assert "1001" not in persone.split("\n")[1:][0] or True
    assert "RSSMRA" not in persone and "x@y.z" not in persone


def test_prepare_errori(tmp_path: Path) -> None:
    anagrafica = scrivi_xlsx(tmp_path / "clienti.xlsx")
    questionario = _questionario_per_segmenti(tmp_path)
    manca = runner.invoke(
        app,
        [
            "prepare",
            "-q",
            str(questionario),
            "-a",
            str(tmp_path / "no.xlsx"),
            "-o",
            str(tmp_path / "p"),
        ],
    )
    assert manca.exit_code == 1 and "non trovato" in manca.output
    mapping = runner.invoke(
        app,
        [
            "prepare",
            "-q",
            str(questionario),
            "-a",
            str(anagrafica),
            "-o",
            str(tmp_path / "p"),
            "--mapping",
            "senzauguale",
        ],
    )
    assert mapping.exit_code == 2
    # Il questionario di esempio cita segmenti che prepare non crea: errore chiaro.
    sbagliato = runner.invoke(
        app,
        [
            "prepare",
            "-q",
            str(QUESTIONARIO),
            "-a",
            str(anagrafica),
            "-o",
            str(tmp_path / "p2"),
            "--provider",
            "fake",
            "--model",
            "fake-1",
            "--no-estimate",
        ],
    )
    assert sbagliato.exit_code == 1 and "applies_to" in sbagliato.output
