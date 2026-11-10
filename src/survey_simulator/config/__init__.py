"""Schema e validazione della configurazione YAML di progetto."""

from survey_simulator.config.loader import (
    ConfigError,
    LoadedConfig,
    load_config,
    parse_config,
    validate_config,
)
from survey_simulator.config.rules import (
    InterviewEstimate,
    Issue,
    Level,
    estimate_interviews,
    segment_sizes,
)
from survey_simulator.config.schema import (
    Allocation,
    Design,
    Mode,
    OutputFormat,
    SurveySimulatorConfig,
)

__all__ = [
    "Allocation",
    "ConfigError",
    "Design",
    "InterviewEstimate",
    "Issue",
    "Level",
    "LoadedConfig",
    "Mode",
    "OutputFormat",
    "SurveySimulatorConfig",
    "estimate_interviews",
    "load_config",
    "parse_config",
    "segment_sizes",
    "validate_config",
]
