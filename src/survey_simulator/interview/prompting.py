"""Rendering dei prompt degli agenti d'intervista (file in agents/prompts/, in italiano)."""

import hashlib
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from survey_simulator.personas.schema import Persona
from survey_simulator.questionnaire.modes import Mode

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "agents" / "prompts"
RESPONDENT_TEMPLATE = "respondent_it.j2"
INTERVIEWER_TEMPLATE = "interviewer_it.j2"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
    autoescape=False,
)


def template_hashes() -> dict[str, str]:
    """Hash dei prompt usati nelle interviste, per il manifest del run."""
    out: dict[str, str] = {}
    for name in (RESPONDENT_TEMPLATE, INTERVIEWER_TEMPLATE):
        path = TEMPLATE_DIR / name
        if path.is_file():
            out[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def render_respondent_system(persona: Persona, mode: Mode, *, nonverbal: bool = True) -> str:
    """System prompt del rispondente: la narrativa della persona più le regole della modalità."""
    return _env.get_template(RESPONDENT_TEMPLATE).render(
        narrative=persona.narrative,
        style=persona.response_style.labels(),
        mode=mode.value,
        nonverbal=nonverbal,
    )


def render_interviewer_system(mode: Mode) -> str:
    """System prompt dell'intervistatore (CATI e CAPI)."""
    return _env.get_template(INTERVIEWER_TEMPLATE).render(mode=mode.value)
