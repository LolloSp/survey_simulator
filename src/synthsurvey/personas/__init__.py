"""Persone: attributi oltre la demografia, stile di risposta, narrativa in italiano."""

from synthsurvey.personas.build import (
    PersonasResult,
    build_personas,
    personas_frame,
    personas_markdown,
)
from synthsurvey.personas.schema import (
    Names,
    Persona,
    Priors,
    Provenance,
    load_names,
    load_priors,
)

__all__ = [
    "Names",
    "Persona",
    "PersonasResult",
    "Priors",
    "Provenance",
    "build_personas",
    "load_names",
    "load_priors",
    "personas_frame",
    "personas_markdown",
]
