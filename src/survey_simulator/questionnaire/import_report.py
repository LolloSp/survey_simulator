"""Esito dell'importazione: YAML sorgente con intestazione e rapporto Markdown per la revisione."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from survey_simulator.questionnaire.export import TIPI
from survey_simulator.questionnaire.importer import ImportResult, NoteKind
from survey_simulator.questionnaire.schema import QuestionType

NOMI_NOTE = {
    NoteKind.ROUTING: "routing interpretato",
    NoteKind.TYPE: "tipo di domanda scelto",
    NoteKind.OPTIONS: "opzioni incerte",
    NoteKind.TEXT: "testo ricostruito",
    NoteKind.ASSUMPTION: "ipotesi",
    NoteKind.SKIPPED: "parti non trascritte",
}

CHECKLIST = [
    "Ogni domanda del documento è presente, nello stesso ordine, con il testo integrale.",
    'Le opzioni sono complete e nell\'ordine originale; "non so" è reso con `dont_know`.',
    "Ogni istruzione di salto del documento corrisponde a uno `show_if` sulle domande giuste.",
    "Scale: estremi ed etichette corrispondono al documento.",
    "Griglie: tutti gli item e la stessa scala del documento.",
    "`applies_to` solo dove il documento limita la domanda a un segmento.",
    "Pagine per la versione web ragionevoli; i filtri non sono separati dalle domande.",
    "Lanciare `survey-simulator questionnaire validate <yaml> --config <config>` "
    "dopo le correzioni.",
]


def to_source_yaml(raw: dict[str, Any], result: ImportResult) -> str:
    """YAML nel formato di M5 con intestazione di provenienza (commento)."""
    quando = datetime.now(UTC).strftime("%Y-%m-%d")
    stato = "valido" if result.valid else "NON VALIDO: vedi rapporto"
    testa = [
        f"# Importato da {result.source.path.name} (sha256 {result.source.sha256[:12]}) "
        f"il {quando} con {result.provider}/{result.model}.",
        "# Bozza prodotta da un agente LLM: da revisionare prima del congelamento.",
        f"# Esito della validazione automatica: {stato}.",
    ]
    corpo = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=100)
    return "\n".join(testa) + "\n" + corpo


def _riga_domanda(q: dict[str, Any], refs: dict[str, str]) -> str:
    tipo = TIPI.get(QuestionType(q["type"]), q["type"]) if q.get("type") else "?"
    n_opt: str
    if q.get("options"):
        n_opt = str(len(q["options"]))
    elif q.get("scale"):
        n_opt = f"scala {q['scale'].get('min')}-{q['scale'].get('max')}"
    else:
        n_opt = ""
    if q.get("items"):
        n_opt = f"{len(q['items'])} item, " + n_opt
    extra = []
    if q.get("dont_know"):
        extra.append("non so")
    if q.get("randomize"):
        extra.append("random")
    if q.get("applies_to"):
        extra.append("solo " + ", ".join(q["applies_to"]))
    if q.get("probe"):
        extra.append("rilancio")
    if q.get("coding_note"):
        extra.append("nota di codifica")
    celle = [
        q.get("id", "?"),
        refs.get(q.get("id", ""), ""),
        tipo,
        n_opt,
        f"`{q['show_if']}`" if q.get("show_if") else "",
        str(q.get("page", "")),
        ", ".join(extra),
    ]
    return "| " + " | ".join(c.replace("|", "\\|") for c in celle) + " |"


def render_report(result: ImportResult, *, yaml_path: Path | None = None) -> str:
    """Rapporto Markdown: provenienza, esito, domande, note dell'agente, errori, checklist."""
    doc = result.source
    s = result.stats.as_dict()
    righe = [
        "# Rapporto di importazione del questionario",
        "",
        "Trascrizione automatica con agente LLM. **La revisione umana è obbligatoria** "
        "prima di usare il questionario e prima del congelamento di un run.",
        "",
        "## Provenienza",
        "",
        f"- Sorgente: `{doc.path.name}` (formato {doc.format}, sha256 `{doc.sha256}`)",
        f"- Testo estratto: {doc.chars} caratteri, {doc.units} "
        + ("pagine/fogli" if doc.units != 1 else "unità"),
        f"- Modello: {result.provider}/{result.model}, effort {result.effort}",
        f"- Prompt dell'agente: `questionnaire_import_it.j2` sha256 `{result.prompt_sha256[:12]}`",
        f"- Giri: {len(result.rounds)} (chiamate reali {s['calls']}, "
        f"dalla cache {s['cache_hits']}); token {s['input_tokens']} in / "
        f"{s['output_tokens']} out; costo {s['cost_usd']:.4f} USD",
    ]
    if yaml_path is not None:
        righe.append(f"- YAML prodotto: `{yaml_path.as_posix()}`")
    for w in doc.warnings:
        righe.append(f"- Avviso di estrazione: {w}")
    righe.append("")
    righe.append("## Esito")
    righe.append("")
    if result.refused:
        righe.append("Il modello ha **rifiutato** la richiesta: nessuna trascrizione prodotta.")
    elif result.valid:
        righe.append("YAML **valido** secondo lo schema, il routing e la configurazione.")
    elif result.raw is not None:
        righe.append(
            "YAML **non valido** dopo i giri di correzione: la bozza è stata salvata, "
            "gli errori sono elencati sotto e vanno corretti a mano."
        )
    else:
        righe.append("Nessuna bozza utilizzabile: il modello non ha prodotto un JSON conforme.")
    for r in result.rounds:
        n = len(r.errors)
        esito = "ok" if not n else ("1 errore" if n == 1 else f"{n} errori")
        righe.append(f"- Giro {r.number}: {esito}")
    righe.append("")
    if result.raw is not None:
        raw = result.raw
        n_dom = sum(len(sz.get("questions", [])) for sz in raw.get("sections", []))
        righe.append("## Questionario trascritto")
        righe.append("")
        righe.append(
            f"`{raw.get('id')}` v{raw.get('version')}, lingua {raw.get('language')}: "
            f"{len(raw.get('sections', []))} sezioni, {n_dom} domande."
        )
        righe.append("")
        righe.append("| id | nel documento | tipo | opzioni | show_if | pagina | note |")
        righe.append("|---|---|---|---|---|---|---|")
        refs = result.source_refs
        for sz in raw.get("sections", []):
            for q in sz.get("questions", []):
                righe.append(_riga_domanda(q, refs))
        righe.append("")
    if result.draft is not None:
        righe.append("## Incertezze segnalate dall'agente")
        righe.append("")
        if not result.draft.notes:
            righe.append("Nessuna nota: l'agente non ha segnalato dubbi. Diffidare comunque.")
        for kind in NoteKind:
            note = [n for n in result.draft.notes if n.kind == kind]
            if not note:
                continue
            righe.append(f"### {NOMI_NOTE[kind].capitalize()}")
            righe.append("")
            for nota in note:
                dove = f"**{nota.question_id}**: " if nota.question_id else ""
                righe.append(f"- {dove}{nota.message}")
            righe.append("")
    if result.errors and not result.refused:
        righe.append("## Errori residui")
        righe.append("")
        righe.extend(f"- {e}" for e in result.errors)
        righe.append("")
    righe.append("## Lista di controllo per la revisione")
    righe.append("")
    righe.extend(f"- [ ] {voce}" for voce in CHECKLIST)
    return "\n".join(righe).rstrip() + "\n"
