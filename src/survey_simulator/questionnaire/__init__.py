"""Questionario: schema, routing con show_if, versioni per modalità, esportazione, importazione."""

from survey_simulator.questionnaire.export import export, to_markdown, to_yaml
from survey_simulator.questionnaire.extract import ExtractedDocument, ExtractionError, extract_text
from survey_simulator.questionnaire.import_report import render_report, to_source_yaml
from survey_simulator.questionnaire.importer import (
    ImportDraft,
    ImportResult,
    ImportRound,
    NoteKind,
    draft_schema,
    draft_to_raw,
    import_questionnaire,
    render_system_prompt,
    validate_raw,
)
from survey_simulator.questionnaire.loader import (
    LoadedQuestionnaire,
    QuestionnaireError,
    check_against_config,
    load_questionnaire,
    parse_questionnaire,
)
from survey_simulator.questionnaire.modes import (
    DONT_KNOW_LABEL,
    Mode,
    ModeQuestion,
    ModeQuestionnaire,
    adapt,
    adapt_all,
    option_order,
)
from survey_simulator.questionnaire.routing import (
    RoutingError,
    evaluate,
    next_question,
    parse,
    route,
    validate_show_if,
)
from survey_simulator.questionnaire.schema import (
    DONT_KNOW_CODE,
    Question,
    Questionnaire,
    QuestionType,
    Scale,
    Section,
)

__all__ = [
    "DONT_KNOW_CODE",
    "DONT_KNOW_LABEL",
    "ExtractedDocument",
    "ExtractionError",
    "ImportDraft",
    "ImportResult",
    "ImportRound",
    "LoadedQuestionnaire",
    "Mode",
    "ModeQuestion",
    "ModeQuestionnaire",
    "NoteKind",
    "Question",
    "QuestionType",
    "Questionnaire",
    "QuestionnaireError",
    "RoutingError",
    "Scale",
    "Section",
    "adapt",
    "adapt_all",
    "check_against_config",
    "draft_schema",
    "draft_to_raw",
    "evaluate",
    "export",
    "extract_text",
    "import_questionnaire",
    "load_questionnaire",
    "next_question",
    "option_order",
    "parse",
    "parse_questionnaire",
    "render_report",
    "render_system_prompt",
    "route",
    "to_markdown",
    "to_source_yaml",
    "to_yaml",
    "validate_raw",
    "validate_show_if",
]
