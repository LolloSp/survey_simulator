"""Agente importatore con client finto: bozza, conversione, giri di correzione, rapporto."""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

from survey_simulator.config import parse_config
from survey_simulator.llm import FakeLLMClient, LLMPool, LLMRequest
from survey_simulator.questionnaire import (
    ExtractedDocument,
    ImportDraft,
    draft_schema,
    draft_to_raw,
    import_questionnaire,
    parse_questionnaire,
    render_report,
    render_system_prompt,
    to_source_yaml,
    validate_raw,
)
from tests.config.conftest import config_base
from tests.questionnaire.draft_example import (
    bozza,
    bozza_rotta,
    bozza_tipo_incoerente,
    domanda,
)

TESTO = "D1. Quanto è soddisfatto?\nScala 1-10\nD2. Perché? (solo voti 1-5)\n"


def documento(testo: str = TESTO) -> ExtractedDocument:
    return ExtractedDocument(
        path=Path("questionario.docx"),
        sha256="ab" * 32,
        format="docx",
        text=testo,
        units=1,
        warnings=["avviso di prova"],
    )


def pool(responder: Any = None, **kw: Any) -> LLMPool:
    return LLMPool(FakeLLMClient("fake-1", responder, **kw))


@pytest.fixture
def config() -> Any:
    return parse_config(config_base())


# --------------------------------------------------------------------------- #
# Schema della bozza e conversione
# --------------------------------------------------------------------------- #


def _oggetti(node: Any) -> list[dict[str, Any]]:
    out = []
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            out.append(node)
        for v in node.values():
            out.extend(_oggetti(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_oggetti(v))
    return out


def test_schema_bozza_adatto_all_output_strutturato() -> None:
    schema = draft_schema()
    oggetti = _oggetti(schema)
    assert len(oggetti) >= 6
    for o in oggetti:
        assert o["additionalProperties"] is False
        assert o["required"] == list(o["properties"]), "tutti i campi obbligatori"
    testo = json.dumps(schema)
    for chiave in ('"default"', '"minimum"', '"pattern"', '"minItems"'):
        assert chiave not in testo
    assert "title" not in schema["$defs"]["DraftQuestion"], "annotazione rimossa"
    assert "title" in schema["$defs"]["DraftSection"]["properties"], "campo conservato"
    jsonschema.validate(bozza(), schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bozza(extra="no"), schema)


def test_conversione_bozza_in_yaml_m5() -> None:
    raw = draft_to_raw(ImportDraft.model_validate(bozza()))
    assert raw["id"] == "energia_2026" and raw["version"] == "1.1"
    d1, d2, _d3, d4 = raw["sections"][0]["questions"]
    assert d1 == {
        "id": "d1",
        "text": "Quanto è soddisfatto del suo attuale fornitore di energia?",
        "type": "scale",
        "scale": {"min": 1, "max": 10, "labels": {1: "Per nulla", 10: "Del tutto"}},
        "dont_know": True,
        "page": 1,
    }
    assert "source_ref" not in d1 and "sensitive" not in d1 and "fixed_last" not in d1
    assert d2["randomize"] is True and d2["fixed_last"] == ["Altro (specificare)"]
    assert d4["max_choices"] == 3 and d4["show_if"] == 'd3 != "No"'
    d5, d6, d8, d10 = raw["sections"][1]["questions"]
    assert d5["items"][0] == {"id": "a", "text": "Le bollette sono facili da capire"}
    assert d5["scale"]["labels"] == {}
    assert d6 == {
        "id": "d6",
        "text": "Quanto spende in media al mese per l'energia?",
        "type": "numeric",
        "min": 0.0,
        "unit": "euro",
        "dont_know": True,
        "page": 5,
    }
    assert d8["applies_to"] == ["pmi"] and d10["sensitive"] is True
    q = parse_questionnaire(raw)
    assert [x.id for x in q.questions] == ["d1", "d2", "d3", "d4", "d5", "d6", "d8", "d10"]


def test_validate_raw_riporta_errori_schema_routing_e_config(config: Any) -> None:
    assert validate_raw(draft_to_raw(ImportDraft.model_validate(bozza())), config) == []
    errori = validate_raw(draft_to_raw(ImportDraft.model_validate(bozza_rotta())), config)
    assert len(errori) == 1 and "q99" in errori[0]
    errori = validate_raw(draft_to_raw(ImportDraft.model_validate(bozza_tipo_incoerente())), config)
    assert len(errori) == 1 and "numeric" in errori[0]
    b = bozza()
    b["sections"][1]["questions"][2]["applies_to"] = ["aziende"]
    errori = validate_raw(draft_to_raw(ImportDraft.model_validate(b)), config)
    assert errori == [
        "applies_to cita segmenti assenti nella config: aziende (disponibili: consumer, pmi)"
    ]
    assert validate_raw(draft_to_raw(ImportDraft.model_validate(b)), None) == []


def test_prompt_di_sistema_elenca_i_segmenti(config: Any) -> None:
    testo = render_system_prompt(config)
    assert "`consumer`: persone residenti in Italia" in testo
    assert "`pmi`: imprese italiane" in testo
    assert "show_if" in testo and "contains" in testo and "answered(" in testo
    assert "nessun segmento definito" in render_system_prompt(None)


# --------------------------------------------------------------------------- #
# Conversazione con l'agente
# --------------------------------------------------------------------------- #


async def test_import_felice(config: Any) -> None:
    p = pool(lambda r: bozza())
    result = await import_questionnaire(documento(), p, config=config)
    assert result.valid and result.errors == [] and not result.refused
    assert len(result.rounds) == 1 and result.rounds[0].errors == []
    assert result.questionnaire is not None and result.questionnaire.id == "energia_2026"
    assert result.source_refs == {
        "d1": "D1",
        "d2": "D2",
        "d3": "D3",
        "d4": "D4",
        "d5": "D5",
        "d6": "D6",
        "d8": "D8",
        "d10": "D10",
    }
    assert result.draft is not None and len(result.draft.notes) == 2
    assert result.provider == "fake" and result.model == "fake-1"
    assert len(result.prompt_sha256) == 64 and result.stats.calls == 1
    client = p.client
    assert isinstance(client, FakeLLMClient)
    req: LLMRequest = client.requests[0]
    assert req.effort == "high" and req.max_tokens == 16_000
    assert req.variant == "import:abababababab:round0"
    assert req.schema == draft_schema()
    assert "`pmi`" in req.system
    assert len(req.messages) == 1 and req.messages[0].role == "user"
    assert "<documento>\n" + TESTO + "</documento>" in req.messages[0].content
    assert req.metadata == {"task": "questionnaire_import", "round": "0"}


async def test_import_corregge_al_secondo_giro(config: Any) -> None:
    def responder(r: LLMRequest) -> dict[str, Any]:
        return bozza_rotta() if len(r.messages) == 1 else bozza()

    p = pool(responder)
    result = await import_questionnaire(documento(), p, config=config, effort="low")
    assert result.valid and len(result.rounds) == 2
    assert result.rounds[0].errors and result.rounds[1].errors == []
    client = p.client
    assert isinstance(client, FakeLLMClient)
    secondo = client.requests[1]
    assert [m.role for m in secondo.messages] == ["user", "assistant", "user"]
    assert secondo.messages[1].content == result.rounds[0].response_text
    assert "non supera la validazione" in secondo.messages[2].content
    assert "q99" in secondo.messages[2].content
    assert secondo.variant.endswith("round1") and secondo.effort == "low"


async def test_import_resta_non_valido_dopo_i_giri(config: Any) -> None:
    p = pool(lambda r: bozza_rotta())
    result = await import_questionnaire(documento(), p, config=config, max_rounds=1)
    assert not result.valid and len(result.rounds) == 2
    assert result.raw is not None and result.draft is not None, "la bozza resta disponibile"
    assert result.errors and result.questionnaire is None
    zero = await import_questionnaire(documento(), pool(lambda r: bozza_rotta()), max_rounds=0)
    assert len(zero.rounds) == 1 and not zero.valid


async def test_import_rifiuto() -> None:
    result = await import_questionnaire(documento(), pool(refuse=True))
    assert result.refused and not result.valid and result.raw is None
    assert len(result.rounds) == 1 and result.errors == ["il modello ha rifiutato la richiesta"]


async def test_import_json_non_conforme_alla_bozza() -> None:
    p = pool(lambda r: {"id": "x", "sections": []})
    result = await import_questionnaire(documento(), p, max_rounds=0)
    assert not result.valid and result.raw is None and result.draft is None
    assert any(e.startswith("language") for e in result.errors)
    testo = pool(lambda r: "non json")
    result = await import_questionnaire(documento(), testo, max_rounds=0)
    assert result.errors == ["risposta non in JSON"]


async def test_import_riusa_la_cache(tmp_path: Path, config: Any) -> None:
    from survey_simulator.llm import ResponseCache

    client = FakeLLMClient("fake-1", lambda r: bozza())
    p = LLMPool(client, cache=ResponseCache(tmp_path))
    await import_questionnaire(documento(), p, config=config)
    await import_questionnaire(documento(), p, config=config)
    assert client.calls == 1 and p.stats.cache_hits == 1
    # Un documento diverso non deve prendere la risposta in cache.
    altro = ExtractedDocument(Path("b.pdf"), "cd" * 32, "pdf", "D1. Altro?", 1)
    await import_questionnaire(altro, p, config=config)
    assert client.calls == 2


# --------------------------------------------------------------------------- #
# YAML e rapporto
# --------------------------------------------------------------------------- #


async def test_yaml_sorgente_con_intestazione(config: Any) -> None:
    result = await import_questionnaire(documento(), pool(lambda r: bozza()), config=config)
    assert result.raw is not None
    testo = to_source_yaml(result.raw, result)
    righe = testo.splitlines()
    assert righe[0].startswith("# Importato da questionario.docx (sha256 abababababab)")
    assert "fake/fake-1" in righe[0]
    assert righe[2] == "# Esito della validazione automatica: valido."
    ricaricato = yaml.safe_load(testo)
    assert ricaricato == result.raw
    assert parse_questionnaire(ricaricato).question("d1").scale is not None


async def test_rapporto_valido(config: Any) -> None:
    result = await import_questionnaire(documento(), pool(lambda r: bozza()), config=config)
    md = render_report(result, yaml_path=Path("out/energia.yaml"))
    assert md.startswith("# Rapporto di importazione del questionario")
    assert "revisione umana è obbligatoria" in md
    assert "`questionario.docx` (formato docx, sha256 `" + "ab" * 32 + "`)" in md
    assert "- Avviso di estrazione: avviso di prova" in md
    assert "- YAML prodotto: `out/energia.yaml`" in md or "YAML prodotto: `out\\energia.yaml`" in md
    assert "YAML **valido**" in md and "- Giro 0: ok" in md
    assert "2 sezioni, 8 domande" in md
    assert "| d2 | D2 | risposta singola | 3 | `d1 <= 5` | 2 | random |" in md
    assert "| d5 | D5 | griglia | 2 item, scala 1-5 |  | 4 | non so |" in md
    assert "| d8 | D8 | risposta singola | 3 |  | 6 | solo pmi |" in md
    assert "### Routing interpretato" in md and '**d4**: "Se No passare alla D5"' in md
    assert "### Parti non trascritte" in md
    assert "## Errori residui" not in md
    assert "- [ ] Ogni istruzione di salto" in md


async def test_rapporto_non_valido_e_rifiuto(config: Any) -> None:
    result = await import_questionnaire(
        documento(), pool(lambda r: bozza_rotta()), config=config, max_rounds=0
    )
    md = render_report(result)
    assert "YAML **non valido**" in md and "## Errori residui" in md
    assert "- Giro 0: 1 errore\n" in md
    assert "q99" in md and "YAML prodotto" not in md
    rifiuto = await import_questionnaire(documento(), pool(refuse=True))
    md_r = render_report(rifiuto)
    assert "**rifiutato**" in md_r and "## Questionario trascritto" not in md_r
    assert "## Errori residui" not in md_r


def test_bozza_con_rilancio_e_nota_di_codifica(config: Any) -> None:
    b = bozza()
    b["sections"][0]["questions"].append(
        domanda(
            id="d9",
            source_ref="D9",
            text="Cosa le porta via più tempo nella gestione dell'attività?",
            type="open",
            probe="E l'energia, dove sta in questa lista?",
            coding_note="Energia citata spontaneamente: sì/no",
            page=2,
        )
    )
    raw = draft_to_raw(ImportDraft.model_validate(b))
    d9 = raw["sections"][0]["questions"][-1]
    assert d9["probe"] == "E l'energia, dove sta in questa lista?"
    assert d9["coding_note"] == "Energia citata spontaneamente: sì/no"
    assert "probe" not in raw["sections"][0]["questions"][0], "assente se null"
    q = parse_questionnaire(raw)
    assert q.question("d9").probe == "E l'energia, dove sta in questa lista?"
    schema = draft_schema()
    assert {"probe", "coding_note"} <= set(schema["$defs"]["DraftQuestion"]["properties"])
    assert "`probe`" in render_system_prompt(config) and "`coding_note`" in render_system_prompt(
        config
    )
