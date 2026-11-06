"""Questionario: schema, routing con show_if, versioni per modalità, esportazione."""

from synthsurvey.questionnaire.export import export, to_markdown, to_yaml
from synthsurvey.questionnaire.loader import (
    LoadedQuestionnaire,
    QuestionnaireError,
    check_against_config,
    load_questionnaire,
    parse_questionnaire,
)
from synthsurvey.questionnaire.modes import (
    DONT_KNOW_LABEL,
    Mode,
    ModeQuestion,
    ModeQuestionnaire,
    adapt,
    adapt_all,
    option_order,
)
from synthsurvey.questionnaire.routing import (
    RoutingError,
    evaluate,
    next_question,
    parse,
    route,
    validate_show_if,
)
from synthsurvey.questionnaire.schema import (
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
    "LoadedQuestionnaire",
    "Mode",
    "ModeQuestion",
    "ModeQuestionnaire",
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
    "evaluate",
    "export",
    "load_questionnaire",
    "next_question",
    "option_order",
    "parse",
    "parse_questionnaire",
    "route",
    "to_markdown",
    "to_yaml",
    "validate_show_if",
]
