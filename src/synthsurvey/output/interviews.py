"""Pagina `interviste.html`: interviste e risposte da leggere, per domanda o per persona.

Un solo file HTML autonomo (dati incorporati come JSON, nessuna risorsa
esterna). Contiene solo persone sintetiche e le loro risposte: mai `unit_id`
né altro che leghi le persone ai record del committente.
"""

import json
from pathlib import Path
from typing import Any

import polars as pl
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from synthsurvey.personas.schema import Persona
from synthsurvey.questionnaire.schema import Questionnaire

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "interviste.html.j2"
MODE_ORDER = ("cawi", "cati", "capi")
SIGNALS = ("esitazione", "incertezza", "entusiasmo", "disinteresse", "irritazione", "imbarazzo")

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    undefined=StrictUndefined,
    autoescape=True,
)


def _str(v: Any) -> str:
    return "" if v is None else str(v)


def _nonverbal(raw: Any) -> tuple[dict[str, int], str]:
    """Intensità > 0 dei segnali emessi e pensiero non detto."""
    if not raw:
        return {}, ""
    try:
        nv = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return {}, ""
    if not isinstance(nv, dict):
        return {}, ""
    livelli = {k: int(nv[k]) for k in SIGNALS if isinstance(nv.get(k), int) and nv[k] > 0}
    return livelli, _str(nv.get("note"))


def _persona(p: Persona) -> dict[str, Any]:
    firm = None
    if p.firm is not None:
        firm = {
            "sector": p.firm.sector.replace("_", " "),
            "employees": p.firm.employees,
            "role": p.firm.respondent_role.replace("_", " "),
        }
    return {
        "id": p.persona_id,
        "segment": p.segment,
        "name": p.name or p.persona_id,
        "sex": p.sex,
        "age": p.age,
        "region": p.region.replace("_", " ").title(),
        "narrative": p.narrative,
        "firm": firm,
    }


def build_interviews_data(
    manifest: dict[str, Any],
    long: pl.DataFrame,
    personas: list[Persona],
    questionnaire: Questionnaire,
    interviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Dati incorporati nella pagina: domande, persone, interviste, risposte."""
    questions = []
    item_text: dict[tuple[str, str], str] = {}
    for section in questionnaire.sections:
        for q in section.questions:
            questions.append({"id": q.id, "text": q.text, "probe": q.probe, "note": q.coding_note})
            for grid_item in q.items or []:
                item_text[(q.id, grid_item.id)] = grid_item.text
    rows = []
    for r in long.iter_rows(named=True):
        livelli, pensiero = _nonverbal(r.get("nonverbal_emitted"))
        item = _str(r.get("item_id"))
        rows.append(
            {
                "p": r["persona_id"],
                "m": r["mode"],
                "r": int(r.get("replicate") or 1),
                "q": r["question_id"],
                "i": item_text.get((r["question_id"], item), item),
                "s": _str(r.get("status")),
                "a": _str(r.get("answer_text")) or _str(r.get("answer_code")),
                "pt": _str(r.get("probe_text")),
                "inc": bool(r.get("incongruence")),
                "nv": livelli,
                "note": pensiero,
            }
        )
    modi_presenti = {row["m"] for row in rows}
    modes = [m for m in MODE_ORDER if m in modi_presenti] + sorted(modi_presenti - set(MODE_ORDER))
    progetto = manifest.get("config", {}).get("project", {}).get("name", "")
    return {
        "run": _str(manifest.get("run_id")),
        "project": _str(progetto),
        "modes": modes,
        "replicates": sorted({row["r"] for row in rows}) or [1],
        "questions": questions,
        "personas": [_persona(p) for p in personas],
        "interviews": [
            {
                "persona_id": i.get("persona_id"),
                "mode": i.get("mode"),
                "replicate": i.get("replicate", 1),
                "completed": bool(i.get("completed")),
            }
            for i in (interviews or [])
        ],
        "rows": rows,
    }


def render_interviews_page(data: dict[str, Any]) -> str:
    return _env.get_template(TEMPLATE_NAME).render(data=data)


def write_interviews_page(data: dict[str, Any], path: Path) -> Path:
    path.write_text(render_interviews_page(data), encoding="utf-8")
    return path


def read_interviews(run_dir: Path) -> list[dict[str, Any]]:
    """`interviews.json` del run, se c'è (i run più vecchi possono non averlo)."""
    p = run_dir / "interviews.json"
    if not p.is_file():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []
