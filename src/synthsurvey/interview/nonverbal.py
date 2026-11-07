"""Segnali non verbali: vocabolario fisso, schema, filtro per modalità, soglie.

È il dato più inventato del sistema (docs/SPEC.md): va letto come ipotesi
qualitativa. Il rispondente emette tutti i segnali (la sua "verità"),
l'intervistatore osserva solo quelli percepibili nella sua modalità.
"""

from typing import Any

from synthsurvey.questionnaire.modes import Mode

SIGNALS = ("esitazione", "incertezza", "entusiasmo", "disinteresse", "irritazione", "imbarazzo")
BODY_FIELDS = ("espressione", "sguardo", "postura", "gesti")
MAX_INTENSITY = 3
PROBE_THRESHOLD = 2  # intensità osservata da cui l'intervistatore valuta un approfondimento


def nonverbal_schema(mode: Mode) -> dict[str, Any]:
    """Blocco strutturato emesso dal rispondente (uguale in CATI e CAPI)."""
    props: dict[str, Any] = {s: {"type": "integer", "enum": [0, 1, 2, 3]} for s in SIGNALS}
    props["body"] = {
        "type": "object",
        "properties": {f: {"type": "string"} for f in BODY_FIELDS},
        "required": list(BODY_FIELDS),
        "additionalProperties": False,
    }
    props["note"] = {"type": "string"}
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


def normalize_emitted(raw: Any) -> dict[str, Any] | None:
    """Blocco emesso ripulito: intensità intere fra 0 e 3, corpo e nota come testo."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    for s in SIGNALS:
        v = raw.get(s, 0)
        try:
            n = int(v)
        except (TypeError, ValueError):
            n = 0
        out[s] = min(MAX_INTENSITY, max(0, n))
    corpo = raw.get("body")
    out["body"] = (
        {f: str(corpo.get(f, "")).strip() for f in BODY_FIELDS} if isinstance(corpo, dict) else None
    )
    nota = raw.get("note")
    out["note"] = str(nota).strip() if isinstance(nota, str) else ""
    return out


def observe(mode: Mode, emitted: dict[str, Any] | None) -> dict[str, Any] | None:
    """Ciò che l'intervistatore percepisce: al telefono niente linguaggio del corpo."""
    if emitted is None:
        return None
    out = {s: emitted[s] for s in SIGNALS}
    if mode is Mode.CAPI and emitted.get("body"):
        out["body"] = dict(emitted["body"])
    return out


def max_intensity(observed: dict[str, Any] | None) -> int:
    if not observed:
        return 0
    return max(int(observed.get(s, 0)) for s in SIGNALS)


def describe_observed(observed: dict[str, Any] | None) -> str:
    """Testo per l'intervistatore e per le trascrizioni."""
    if not observed:
        return "nessun segnale rilevato"
    attivi = [f"{s} {observed[s]}" for s in SIGNALS if observed.get(s)]
    testo = ", ".join(attivi) if attivi else "voce neutra"
    corpo = observed.get("body")
    if isinstance(corpo, dict):
        parti = [f"{k}: {v}" for k, v in corpo.items() if v]
        if parti:
            testo += "; corpo: " + "; ".join(parti)
    return testo
