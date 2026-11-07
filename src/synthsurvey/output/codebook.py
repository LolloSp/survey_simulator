"""Codebook JSON del run: variabili del dataset largo, valori, mancanti, provenienza."""

import json
from pathlib import Path
from typing import Any

from synthsurvey.output.wide import KEY_COLUMNS, MISSING_LABELS, PERSONA_COLUMNS, WideVariable
from synthsurvey.personas.schema import Persona
from synthsurvey.questionnaire.schema import Questionnaire
from synthsurvey.runner.outputs import LONG_SCHEMA

KEY_LABELS = {
    "persona_id": "Identificativo della persona sintetica",
    "mode": "Modalità di intervista (cawi, cati, capi)",
    "replicate": "Numero di replica dell'intervista",
    "model": "Modello linguistico usato",
}
PERSONA_LABELS = {
    "segment": "Segmento di campionamento",
    "region": "Regione di residenza",
    "macro_area": "Ripartizione geografica",
    "sex": "Sesso",
    "age": "Età in anni",
    "age_band": "Classe di età",
    "education": "Titolo di studio",
    "employment": "Condizione professionale",
    "income_quintile": "Quintile di reddito familiare",
    "sector": "Settore dell'impresa (solo imprese)",
    "size_class": "Classe dimensionale dell'impresa (solo imprese)",
    "respondent_role": "Ruolo del rispondente nell'impresa (solo imprese)",
    "weight": "Peso di post-stratificazione (somma = numerosità del campione)",
    "weight_pop": "Peso riportato alla popolazione",
}
PROVENANCE_NOTES = {
    "campione": "dal campione per quote (ISTAT via IPF)",
    "istat": "estratto da una distribuzione ISTAT condizionata al profilo",
    "istat_proxy": "distribuzione ISTAT di un gruppo vicino",
    "ipotesi": "priori dichiarati in YAML, nessuna fonte statistica (IPOTESI)",
}


def _provenance_summary(personas: list[Persona]) -> dict[str, str]:
    """Per ogni attributo, la provenienza più frequente fra le persone."""
    conteggi: dict[str, dict[str, int]] = {}
    for p in personas:
        for attr, prov in p.provenance.items():
            conteggi.setdefault(attr, {})
            conteggi[attr][prov.value] = conteggi[attr].get(prov.value, 0) + 1
    return {a: max(c, key=lambda k: c[k]) for a, c in conteggi.items()}


def build_codebook(
    run_id: str,
    questionnaire: Questionnaire,
    variables: list[WideVariable],
    personas: list[Persona],
    *,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provenienza = _provenance_summary(personas)
    persona_vars = []
    for col in PERSONA_COLUMNS:
        prov = provenienza.get(col)
        persona_vars.append(
            {
                "name": col,
                "label": PERSONA_LABELS.get(col, col),
                "provenance": prov,
                "provenance_note": PROVENANCE_NOTES.get(prov, "") if prov else "",
            }
        )
    tratti = [
        {"name": a, "provenance": p, "provenance_note": PROVENANCE_NOTES.get(p, "")}
        for a, p in sorted(provenienza.items())
        if a not in PERSONA_COLUMNS
    ]
    variabili = []
    for v in variables:
        voce: dict[str, Any] = {
            "name": v.name,
            "question_id": v.question_id,
            "item_id": v.item_id,
            "option_index": v.option_index,
            "kind": v.kind,
            "label": v.label,
            "values": {str(k): lab for k, lab in v.values.items()},
        }
        if v.kind not in ("open",):
            voce["missing"] = {str(k): lab for k, lab in MISSING_LABELS.items()}
        variabili.append(voce)
    return {
        "run_id": run_id,
        "disclaimer": (
            "Dati SIMULATI da persone sintetiche e modelli linguistici: non sono risposte di "
            "persone reali. Le modalità senza controparte reale sono stime non validate."
        ),
        "questionnaire": {
            "id": questionnaire.id,
            "version": questionnaire.version,
            "language": questionnaire.language,
            "sha256": (manifest or {}).get("questionnaire", {}).get("sha256"),
        },
        "models": (manifest or {}).get("models", []),
        "missing_codes": {str(k): v for k, v in MISSING_LABELS.items()},
        "wide": {
            "row": "una riga per persona x modalità x replica x modello",
            "keys": [{"name": k, "label": KEY_LABELS[k]} for k in KEY_COLUMNS],
            "persona_variables": persona_vars,
            "variables": variabili,
        },
        "long": {
            "row": "una riga per domanda e item di ogni intervista",
            "columns": list(LONG_SCHEMA),
            "status_values": [
                "answered",
                "dont_know",
                "nonresponse",
                "not_applicable",
                "abandoned",
            ],
        },
        "persona_traits_provenance": tratti,
    }


def write_codebook(codebook: dict[str, Any], path: Path) -> Path:
    path.write_text(json.dumps(codebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
