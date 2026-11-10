"""Provider `session` (M14): cassetta su file, pausa e ripresa del run e del pilota."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from survey_simulator.cli import app
from survey_simulator.config import load_config, parse_config
from survey_simulator.llm import (
    AwaitingAnswersError,
    LLMError,
    LLMRequest,
    Message,
    SessionClient,
    SessionMailbox,
    fill_schema,
    make_client,
    pending_markdown,
    session_mailbox_dir,
)
from survey_simulator.population.tables import load_tables
from survey_simulator.runner import execute_run, read_manifest
from tests.config.conftest import ESEMPI_DIR, config_base

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
QUESTIONARIO = ESEMPI_DIR.parent.parent / "questionnaires" / "examples" / "mercato_v1.yaml"
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string", "enum": ["a", "b"]}},
    "required": ["answer"],
    "additionalProperties": False,
}
runner = CliRunner()


def richiesta(testo: str = "Domanda?") -> LLMRequest:
    return LLMRequest(
        system="Sei una persona.",
        messages=(Message("user", testo),),
        schema=SCHEMA,
        metadata={"persona": "p_00001", "step": "q:q1:a"},
        variant="v1",
    )


async def test_cassetta_pausa_e_risposta(tmp_path: Path) -> None:
    mailbox = SessionMailbox(tmp_path / "session")
    client = SessionClient(mailbox)
    req = richiesta()
    fp = req.fingerprint("session", "session")
    with pytest.raises(AwaitingAnswersError) as info:
        await client.complete(req)
    assert info.value.fingerprint == fp and info.value.path.is_file()
    in_attesa = mailbox.pending()
    assert len(in_attesa) == 1 and in_attesa[0].metadata["persona"] == "p_00001"
    assert in_attesa[0].last_user_message == "Domanda?" and in_attesa[0].schema == SCHEMA
    md = pending_markdown(in_attesa, full=True)
    assert fp in md and "### Schema della risposta" in md and "Sei una persona." in md
    breve = pending_markdown(in_attesa, full=False)
    assert "Domanda?" in breve and "### System" not in breve
    # Seconda chiamata: non duplica il file in attesa.
    with pytest.raises(AwaitingAnswersError):
        await client.complete(req)
    assert mailbox.counts() == (1, 0)
    # Risposta non conforme rifiutata, poi quella giusta accettata.
    ok, errori = mailbox.deposit({fp: {"answer": "z"}})
    assert ok == [] and len(errori) == 1 and "non conforme" in errori[0]
    ok, errori = mailbox.deposit({fp: {"answer": "b"}, "sconosciuta": {"x": 1}})
    assert ok == [fp, "sconosciuta"] and errori == []
    assert mailbox.counts() == (0, 2)
    out = await client.complete(req)
    assert out.parsed == {"answer": "b"} and out.provider == "session" and out.model == "session"
    assert out.usage.input_tokens > 0 and out.usage.output_tokens > 0
    # Una risposta depositata a mano ma incoerente con lo schema: errore esplicito.
    mailbox.answer_path(fp).write_text(json.dumps({"parsed": {"answer": 5}, "text": ""}))
    with pytest.raises(LLMError, match="non conforme"):
        await client.complete(req)
    testo = SessionClient(mailbox)
    libera = LLMRequest(system="s", messages=(Message("user", "ciao"),), schema=None)
    fpl = libera.fingerprint("session", "session")
    mailbox.deposit({fpl: "risposta libera"})
    out = await testo.complete(libera)
    assert out.text == "risposta libera" and out.parsed is None


def test_registro_e_prezzo_zero(tmp_path: Path) -> None:
    raw = config_base()
    raw["engine"]["models"] = [{"provider": "session", "model": "session"}]
    raw["engine"]["cache_dir"] = str(tmp_path / "cache")
    cfg = parse_config(raw)
    client = make_client(cfg.engine.models[0], cfg)
    assert isinstance(client, SessionClient)
    assert session_mailbox_dir(cfg) == tmp_path / "cache" / "session"
    from survey_simulator.llm import default_pricing

    assert default_pricing().estimate_usd("session", 1000, 1000) == 0.0


def _config(tmp_path: Path) -> Path:
    raw = yaml.safe_load((ESEMPI_DIR / "mercato_100.yaml").read_text(encoding="utf-8"))
    raw["engine"]["models"] = [{"provider": "session", "model": "session"}]
    raw["engine"]["replicates"] = 1
    raw["modes"]["enabled"] = ["cawi"]
    raw["run"]["pilot_size"] = 3
    raw["questionnaire"]["path"] = str(QUESTIONARIO)
    raw["output"]["dir"] = str(tmp_path / "runs")
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path


def _rispondi_a_tutto(mailbox: SessionMailbox) -> int:
    """Simula la sessione: riempie ogni schema in attesa con il primo valore ammesso."""
    risposte: dict[str, Any] = {}
    for r in mailbox.pending():
        assert r.schema is not None
        out = fill_schema(r.schema)
        if "abandon" in out:
            out["abandon"] = False
            out["abandon_reason"] = None
        risposte[r.fingerprint] = out
    ok, errori = mailbox.deposit(risposte)
    assert errori == []
    return len(ok)


def test_run_in_pausa_e_ripresa(tmp_path: Path) -> None:
    path = _config(tmp_path)
    loaded = load_config(path)
    tables = load_tables(PROCESSED)
    mailbox = SessionMailbox(session_mailbox_dir(loaded.config))
    giri = 0
    while True:
        result = execute_run(
            loaded, data_dir=PROCESSED.parent, pilot=True, run_id="sessione", tables=tables
        )
        if not result.paused:
            break
        giri += 1
        assert giri < 20, "troppi giri: le risposte non vengono riprese"
        m = read_manifest(result.run_dir)
        assert m is not None and m["status"] == "paused"
        assert m["interviews_awaiting"] == (3 if giri == 1 else m["interviews_awaiting"]) >= 1
        assert _rispondi_a_tutto(mailbox) >= 1
    assert giri >= 4, "una pagina CAWI per giro"
    assert len(result.results) == 3 and result.manifest["status"] == "completed"
    assert (result.run_dir / "report.html").is_file()
    assert all(r.model == "session" for res in result.results for r in res.records)
    assert mailbox.counts()[0] == 0


def test_cli_session_e_pilota(tmp_path: Path) -> None:
    path = _config(tmp_path)
    cfg = load_config(path).config
    out = tmp_path / "pilota"
    primo = runner.invoke(
        app,
        ["interview", "preview", "-c", str(path), "--mode", "cawi", "--n", "2", "--out", str(out)],
    )
    assert primo.exit_code == 5, primo.output
    assert "In pausa: 2 interviste aspettano 2 risposte" in primo.output
    elenco = runner.invoke(app, ["session", "list", "-c", str(path)])
    assert elenco.exit_code == 0 and "Richieste in attesa: 2" in elenco.output
    su_file = runner.invoke(
        app, ["session", "list", "-c", str(path), "--full", "--out", str(tmp_path / "attesa.md")]
    )
    assert su_file.exit_code == 0 and (tmp_path / "attesa.md").is_file()
    mailbox = SessionMailbox(session_mailbox_dir(cfg))
    richieste = mailbox.pending()
    risposte = {richieste[0].fingerprint: {"non": "valida"}}
    (tmp_path / "r.json").write_text(json.dumps(risposte), encoding="utf-8")
    rifiuto = runner.invoke(app, ["session", "answer", str(tmp_path / "r.json"), "-c", str(path)])
    assert rifiuto.exit_code == 2 and "rifiutate 1" in rifiuto.output
    for _ in range(12):
        n = _rispondi_a_tutto(mailbox)
        esito = runner.invoke(
            app,
            [
                "interview",
                "preview",
                "-c",
                str(path),
                "--mode",
                "cawi",
                "--n",
                "2",
                "--out",
                str(out),
            ],
        )
        if esito.exit_code == 0:
            break
        assert esito.exit_code == 5 and n >= 1
    assert esito.exit_code == 0, esito.output
    assert "Interviste CAWI: 2 persone, 2 completate" in esito.output
    (tmp_path / "rotto.json").write_text("[1, 2]", encoding="utf-8")
    lista = runner.invoke(app, ["session", "answer", str(tmp_path / "rotto.json"), "-c", str(path)])
    assert lista.exit_code == 1
