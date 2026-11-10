"""Agente importatore: dal testo grezzo di un questionario allo YAML strutturato di M5.

Il modello risponde con una *bozza* (`ImportDraft`), uno schema vicino a quello
finale ma adatto all'output strutturato dei provider: etichette di scala come
lista di coppie, campi facoltativi espliciti, nessun vincolo numerico o di
pattern nello schema inviato. La bozza viene convertita nel dizionario YAML di
M5 e validata con il parser vero; gli errori tornano al modello per un nuovo
giro, fino a `max_rounds` correzioni. La revisione umana resta obbligatoria.
"""

import copy
import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel, ConfigDict, ValidationError

from survey_simulator.config.schema import SurveySimulatorConfig
from survey_simulator.llm.client import Effort, LLMRequest, LLMResponse, Message
from survey_simulator.llm.pool import LLMPool, PoolStats
from survey_simulator.questionnaire.extract import ExtractedDocument
from survey_simulator.questionnaire.loader import (
    QuestionnaireError,
    check_against_config,
    parse_questionnaire,
)
from survey_simulator.questionnaire.schema import Questionnaire, QuestionType

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "agents" / "prompts"
TEMPLATE_NAME = "questionnaire_import_it.j2"
DEFAULT_EFFORT: Effort = "high"
DEFAULT_MAX_TOKENS = 16_000
DEFAULT_MAX_ROUNDS = 2

# --------------------------------------------------------------------------- #
# Bozza: ciò che il modello restituisce
# --------------------------------------------------------------------------- #


class _Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NoteKind(StrEnum):
    ROUTING = "routing"
    TYPE = "type"
    OPTIONS = "options"
    TEXT = "text"
    ASSUMPTION = "assumption"
    SKIPPED = "skipped"


class DraftScaleLabel(_Draft):
    point: int
    label: str


class DraftScale(_Draft):
    min: int
    max: int
    labels: list[DraftScaleLabel]


class DraftItem(_Draft):
    id: str
    text: str


class DraftQuestion(_Draft):
    id: str
    source_ref: str | None
    text: str
    type: QuestionType
    options: list[str] | None
    max_choices: int | None
    scale: DraftScale | None
    items: list[DraftItem] | None
    min: float | None
    max: float | None
    unit: str | None
    sensitive: bool
    applies_to: list[str] | None
    show_if: str | None
    dont_know: bool
    randomize: bool
    fixed_last: list[str]
    page: int | None
    probe: str | None
    coding_note: str | None


class DraftSection(_Draft):
    id: str
    title: str | None
    questions: list[DraftQuestion]


class DraftNote(_Draft):
    question_id: str | None
    kind: NoteKind
    message: str


class ImportDraft(_Draft):
    id: str
    language: str
    version: str
    sections: list[DraftSection]
    notes: list[DraftNote]


_UNSUPPORTED_KEYS = {
    "default",
    "title",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
}


def _strict(node: Any, *, keep_keys: bool = False) -> Any:
    """Schema adatto all'output strutturato: tutto obbligatorio, niente extra.

    `keep_keys` vale dentro `properties` e `$defs`, dove le chiavi sono nomi
    di campi o di modelli e non parole dello schema (un campo `title` resta).
    """
    if isinstance(node, dict):
        if keep_keys:
            return {k: _strict(v) for k, v in node.items()}
        out = {
            k: _strict(v, keep_keys=k in ("properties", "$defs"))
            for k, v in node.items()
            if k not in _UNSUPPORTED_KEYS
        }
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"])
        return out
    if isinstance(node, list):
        return [_strict(v) for v in node]
    return node


def draft_schema() -> dict[str, Any]:
    """JSON Schema della bozza, nella forma accettata dai provider."""
    schema: dict[str, Any] = _strict(ImportDraft.model_json_schema())
    return schema


# --------------------------------------------------------------------------- #
# Dalla bozza al dizionario YAML di M5
# --------------------------------------------------------------------------- #


def draft_to_raw(draft: ImportDraft) -> dict[str, Any]:
    """Dizionario nel formato YAML di docs/SPEC.md: solo i campi significativi."""
    sezioni = []
    for s in draft.sections:
        domande = []
        for q in s.questions:
            d: dict[str, Any] = {"id": q.id, "text": q.text, "type": q.type.value}
            if q.options is not None:
                d["options"] = list(q.options)
            if q.max_choices is not None:
                d["max_choices"] = q.max_choices
            if q.scale is not None:
                d["scale"] = {
                    "min": q.scale.min,
                    "max": q.scale.max,
                    "labels": {lbl.point: lbl.label for lbl in q.scale.labels},
                }
            if q.items is not None:
                d["items"] = [{"id": i.id, "text": i.text} for i in q.items]
            for k in ("min", "max", "unit"):
                v = getattr(q, k)
                if v is not None:
                    d[k] = v
            if q.sensitive:
                d["sensitive"] = True
            if q.applies_to is not None:
                d["applies_to"] = list(q.applies_to)
            if q.show_if:
                d["show_if"] = q.show_if
            if q.dont_know:
                d["dont_know"] = True
            if q.randomize:
                d["randomize"] = True
            if q.fixed_last:
                d["fixed_last"] = list(q.fixed_last)
            if q.page is not None:
                d["page"] = q.page
            if q.probe:
                d["probe"] = q.probe
            if q.coding_note:
                d["coding_note"] = q.coding_note
            domande.append(d)
        sez: dict[str, Any] = {"id": s.id}
        if s.title:
            sez["title"] = s.title
        sez["questions"] = domande
        sezioni.append(sez)
    return {
        "id": draft.id,
        "language": draft.language,
        "version": draft.version,
        "sections": sezioni,
    }


def validate_raw(raw: dict[str, Any], config: SurveySimulatorConfig | None) -> list[str]:
    """Errori del parser M5 (schema, routing) più la coerenza con la config."""
    try:
        q = parse_questionnaire(raw)
    except QuestionnaireError as exc:
        return list(exc.issues)
    return check_against_config(q, config) if config is not None else []


# --------------------------------------------------------------------------- #
# Conversazione con il modello
# --------------------------------------------------------------------------- #

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    autoescape=False,
)

_SOURCE_DESCRIPTIONS = {
    "istat_individui": "persone residenti in Italia (consumatori, cittadini)",
    "istat_imprese": "imprese italiane, risponde chi la rappresenta",
}


def template_hash() -> str:
    return hashlib.sha256((TEMPLATE_DIR / TEMPLATE_NAME).read_bytes()).hexdigest()


def render_system_prompt(config: SurveySimulatorConfig | None) -> str:
    segmenti = []
    if config is not None:
        for name, seg in config.sample.segments.items():
            descr = _SOURCE_DESCRIPTIONS.get(seg.source, seg.source)
            segmenti.append({"name": name, "description": descr})
    if not segmenti:
        segmenti.append({"name": "tutti", "description": "nessun segmento definito nel progetto"})
    return _env.get_template(TEMPLATE_NAME).render(segments=segmenti)


def _user_message(doc: ExtractedDocument) -> str:
    return (
        f"Documento: {doc.path.name} (formato {doc.format}).\n"
        "Trascrivi il questionario seguente nel formato richiesto.\n\n"
        "<documento>\n"
        f"{doc.text}"
        "</documento>"
    )


def _fix_message(errors: list[str]) -> str:
    elenco = "\n".join(f"- {e}" for e in errors)
    return (
        "La trascrizione non supera la validazione. Errori:\n"
        f"{elenco}\n\n"
        "Correggi solo ciò che serve e restituisci di nuovo il questionario completo, "
        "con le note aggiornate."
    )


@dataclass(frozen=True)
class ImportRound:
    number: int
    errors: list[str]  # errori trovati nella risposta di questo giro
    refused: bool
    response_text: str


@dataclass
class ImportResult:
    source: ExtractedDocument
    provider: str
    model: str
    effort: Effort
    rounds: list[ImportRound] = field(default_factory=list)
    draft: ImportDraft | None = None
    raw: dict[str, Any] | None = None
    questionnaire: Questionnaire | None = None
    errors: list[str] = field(default_factory=list)
    stats: PoolStats = field(default_factory=PoolStats)
    prompt_sha256: str = ""

    @property
    def valid(self) -> bool:
        return self.questionnaire is not None

    @property
    def refused(self) -> bool:
        return bool(self.rounds) and self.rounds[-1].refused

    @property
    def source_refs(self) -> dict[str, str]:
        if self.draft is None:
            return {}
        return {
            q.id: q.source_ref for s in self.draft.sections for q in s.questions if q.source_ref
        }


def _parse_draft(response: LLMResponse) -> tuple[ImportDraft | None, list[str]]:
    if response.parsed is None:
        return None, ["risposta non in JSON"]
    try:
        return ImportDraft.model_validate(response.parsed), []
    except ValidationError as exc:
        return None, [
            ".".join(str(p) for p in e["loc"]) + ": " + e["msg"]
            for e in exc.errors(include_url=False)
        ]


async def import_questionnaire(
    doc: ExtractedDocument,
    pool: LLMPool,
    *,
    config: SurveySimulatorConfig | None = None,
    effort: Effort = DEFAULT_EFFORT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> ImportResult:
    """Trascrive il documento con l'agente e ripete sugli errori di validazione.

    `max_rounds` è il numero massimo di giri di correzione dopo il primo.
    Il risultato è sempre restituito: `valid` dice se lo YAML è utilizzabile.
    """
    system = render_system_prompt(config)
    schema = draft_schema()
    result = ImportResult(
        source=doc,
        provider=pool.client.provider,
        model=pool.client.model,
        effort=effort,
        prompt_sha256=template_hash(),
    )
    messages: list[Message] = [Message("user", _user_message(doc))]
    for n in range(max_rounds + 1):
        request = LLMRequest(
            system=system,
            messages=tuple(messages),
            schema=schema,
            max_tokens=max_tokens,
            effort=effort,
            variant=f"import:{doc.sha256[:12]}:round{n}",
            metadata={"task": "questionnaire_import", "round": str(n)},
        )
        response = await pool.complete(request)
        if response.refused:
            result.rounds.append(ImportRound(n, ["il modello ha rifiutato"], True, ""))
            result.errors = ["il modello ha rifiutato la richiesta"]
            break
        draft, errori = _parse_draft(response)
        raw = None
        if draft is not None:
            raw = draft_to_raw(draft)
            errori = validate_raw(raw, config)
        result.rounds.append(ImportRound(n, errori, False, response.text))
        if draft is not None:
            result.draft, result.raw = draft, raw
        result.errors = errori
        if not errori and raw is not None:
            result.questionnaire = parse_questionnaire(copy.deepcopy(raw))
            break
        messages.append(Message("assistant", response.text))
        messages.append(Message("user", _fix_message(errori)))
    result.stats = pool.stats
    return result
