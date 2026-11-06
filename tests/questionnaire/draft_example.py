"""Bozza di esempio come la restituirebbe l'agente importatore (tutti i campi espliciti)."""

import copy
from typing import Any


def domanda(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "q",
        "source_ref": None,
        "text": "Testo",
        "type": "single",
        "options": None,
        "max_choices": None,
        "scale": None,
        "items": None,
        "min": None,
        "max": None,
        "unit": None,
        "sensitive": False,
        "applies_to": None,
        "show_if": None,
        "dont_know": False,
        "randomize": False,
        "fixed_last": [],
        "page": None,
    }
    base.update(kw)
    return base


BOZZA: dict[str, Any] = {
    "id": "energia_2026",
    "language": "it",
    "version": "1.1",
    "sections": [
        {
            "id": "a",
            "title": "Fornitura di energia",
            "questions": [
                domanda(
                    id="d1",
                    source_ref="D1",
                    text="Quanto è soddisfatto del suo attuale fornitore di energia?",
                    type="scale",
                    scale={
                        "min": 1,
                        "max": 10,
                        "labels": [
                            {"point": 1, "label": "Per nulla"},
                            {"point": 10, "label": "Del tutto"},
                        ],
                    },
                    dont_know=True,
                    page=1,
                ),
                domanda(
                    id="d2",
                    source_ref="D2",
                    text="Qual è il motivo principale della sua insoddisfazione?",
                    options=["Prezzo", "Servizio clienti", "Altro (specificare)"],
                    randomize=True,
                    fixed_last=["Altro (specificare)"],
                    show_if="d1 <= 5",
                    page=2,
                ),
                domanda(
                    id="d3",
                    source_ref="D3",
                    text="Negli ultimi 12 mesi ha provato a cambiare fornitore?",
                    options=["Sì, ho cambiato", "Ci ho provato ma non ho cambiato", "No"],
                    page=2,
                ),
                domanda(
                    id="d4",
                    source_ref="D4",
                    text="Quali canali ha usato per informarsi?",
                    type="multi",
                    options=["Sito del fornitore", "Comparatori online", "Nessuno"],
                    max_choices=3,
                    fixed_last=["Nessuno"],
                    show_if='d3 != "No"',
                    page=3,
                ),
            ],
        },
        {
            "id": "b",
            "title": "Giudizi",
            "questions": [
                domanda(
                    id="d5",
                    source_ref="D5",
                    text="Quanto è d'accordo con le seguenti affermazioni?",
                    type="grid",
                    items=[
                        {"id": "a", "text": "Le bollette sono facili da capire"},
                        {"id": "b", "text": "Cambiare fornitore è semplice"},
                    ],
                    scale={"min": 1, "max": 5, "labels": []},
                    dont_know=True,
                    page=4,
                ),
                domanda(
                    id="d6",
                    source_ref="D6",
                    text="Quanto spende in media al mese per l'energia?",
                    type="numeric",
                    min=0.0,
                    unit="euro",
                    dont_know=True,
                    page=5,
                ),
                domanda(
                    id="d8",
                    source_ref="D8",
                    text="Nella sua impresa chi decide il fornitore di energia?",
                    options=["Il titolare", "L'amministrazione", "Altro"],
                    applies_to=["pmi"],
                    page=6,
                ),
                domanda(
                    id="d10",
                    source_ref="D10",
                    text="Quale fascia di reddito familiare la descrive meglio?",
                    options=["Fino a 1.500 euro", "Oltre 1.500 euro"],
                    sensitive=True,
                    dont_know=True,
                    page=7,
                ),
            ],
        },
    ],
    "notes": [
        {
            "question_id": "d4",
            "kind": "routing",
            "message": '"Se No passare alla D5" tradotto in show_if su D4.',
        },
        {
            "question_id": None,
            "kind": "skipped",
            "message": "Lettera di presentazione e ringraziamento finale non trascritti.",
        },
    ],
}


def bozza(**modifiche: Any) -> dict[str, Any]:
    """Copia della bozza, con eventuali chiavi di primo livello sostituite."""
    b = copy.deepcopy(BOZZA)
    b.update(modifiche)
    return b


def bozza_rotta() -> dict[str, Any]:
    """Bozza con un errore di routing: show_if cita una domanda inesistente."""
    b = bozza()
    b["sections"][0]["questions"][1]["show_if"] = "q99 <= 5"
    return b


def bozza_tipo_incoerente() -> dict[str, Any]:
    """Bozza con un errore di schema: domanda numerica con options."""
    b = bozza()
    b["sections"][1]["questions"][1]["options"] = ["a", "b"]
    return b
