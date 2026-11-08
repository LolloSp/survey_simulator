"""Esportazione delle versioni per modalità in YAML e Markdown, per la revisione."""

import hashlib
from dataclasses import asdict
from pathlib import Path

import yaml

from synthsurvey.questionnaire.modes import DONT_KNOW_LABEL, Mode, ModeQuestionnaire
from synthsurvey.questionnaire.schema import QuestionType

TIPI = {
    QuestionType.SINGLE: "risposta singola",
    QuestionType.MULTI: "risposta multipla",
    QuestionType.SCALE: "scala",
    QuestionType.GRID: "griglia",
    QuestionType.OPEN: "aperta",
    QuestionType.NUMERIC: "numerica",
}
NOMI_MODALITA = {
    Mode.CAWI: "CAWI (questionario web autocompilato)",
    Mode.CATI: "CATI (intervista telefonica)",
    Mode.CAPI: "CAPI (intervista di persona)",
}


def to_dict(mq: ModeQuestionnaire) -> dict[str, object]:
    return {
        "mode": mq.mode.value,
        "questionnaire_id": mq.questionnaire_id,
        "version": mq.version,
        "pages": {int(k): v for k, v in mq.pages.items()},
        "questions": [
            {
                k: (v.value if isinstance(v, QuestionType) else v)
                for k, v in asdict(q).items()
                if k != "scale"
            }
            | {"scale": q.scale.model_dump() if q.scale else None}
            for q in mq.questions
        ],
    }


def to_yaml(mq: ModeQuestionnaire) -> str:
    return yaml.safe_dump(to_dict(mq), allow_unicode=True, sort_keys=False)


def to_markdown(mq: ModeQuestionnaire) -> str:
    righe = [
        f"# {mq.questionnaire_id} v{mq.version} — versione {NOMI_MODALITA[mq.mode]}",
        "",
        "Versione generata automaticamente: da rivedere prima del congelamento.",
        "",
    ]
    pagina_di = {qid: p for p, ids in mq.pages.items() for qid in ids}
    pagina_corrente = None
    for q in mq.questions:
        if mq.mode is Mode.CAWI and pagina_di.get(q.id) != pagina_corrente:
            pagina_corrente = pagina_di.get(q.id)
            righe.append(f"## Pagina {pagina_corrente}")
            righe.append("")
        righe.append(f"### {q.id} ({TIPI[q.type]})")
        condizioni = []
        if q.applies_to:
            condizioni.append(f"solo segmenti: {', '.join(q.applies_to)}")
        if q.show_if:
            condizioni.append(f"se `{q.show_if}`")
        if q.sensitive:
            condizioni.append("sensibile")
        if condizioni:
            righe.append(f"*{'; '.join(condizioni)}*")
        righe.append("")
        righe.append(q.text)
        righe.append("")
        if q.items:
            for iid, testo in q.items:
                righe.append(f"- {iid}: {testo}")
            righe.append("")
        if q.options:
            etichetta = "Opzioni" + (" (ordine randomizzato per intervista)" if q.randomize else "")
            righe.append(f"{etichetta}:")
            for o in q.options:
                righe.append(f"- {o}")
            if q.dont_know_visible:
                righe.append(f"- {DONT_KNOW_LABEL}")
            righe.append("")
        if q.scale and not q.options:
            etichette = ", ".join(f"{k} = {v}" for k, v in sorted(q.scale.labels.items()))
            righe.append(
                f"Scala {q.scale.min}-{q.scale.max}" + (f": {etichette}" if etichette else "")
            )
            if q.dont_know_visible:
                righe.append(f"- {DONT_KNOW_LABEL}")
            righe.append("")
        if q.type == QuestionType.NUMERIC:
            limiti = []
            if q.numeric_min is not None:
                limiti.append(f"min {q.numeric_min:g}")
            if q.numeric_max is not None:
                limiti.append(f"max {q.numeric_max:g}")
            if q.unit:
                limiti.append(q.unit)
            righe.append("Numero" + (f" ({', '.join(limiti)})" if limiti else ""))
            if q.dont_know_visible:
                righe.append(f"- {DONT_KNOW_LABEL}")
            righe.append("")
        if q.show_card:
            righe.append("**Cartellino**")
            righe.append("")
        if q.interviewer_note:
            righe.append(f"> Intervistatore: {q.interviewer_note}")
            righe.append("")
        if q.probe:
            righe.append(f"> Rilancio (una sola volta, dopo la risposta spontanea): «{q.probe}»")
            righe.append("")
        if q.coding_note:
            righe.append(f"> Per l'analisi: {q.coding_note}")
            righe.append("")
    return "\n".join(righe).rstrip() + "\n"


def export(mq: ModeQuestionnaire, out_dir: Path) -> dict[str, str]:
    """Scrive `<id>_<mode>.yaml` e `.md`; restituisce gli hash dei file scritti."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{mq.questionnaire_id}_{mq.mode.value}"
    hashes: dict[str, str] = {}
    for suffisso, testo in ((".yaml", to_yaml(mq)), (".md", to_markdown(mq))):
        path = out_dir / f"{stem}{suffisso}"
        dati = testo.encode("utf-8")
        path.write_bytes(dati)
        hashes[path.name] = hashlib.sha256(dati).hexdigest()
    return hashes
