"""Schema e validazione della configurazione YAML di progetto."""

from synthsurvey.config.loader import (
    ConfigError,
    LoadedConfig,
    load_config,
    parse_config,
    validate_config,
)
from synthsurvey.config.rules import (
    InterviewEstimate,
    Issue,
    Level,
    estimate_interviews,
    segment_sizes,
)
from synthsurvey.config.schema import (
    Allocation,
    Design,
    Mode,
    OutputFormat,
    SynthSurveyConfig,
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
    "SynthSurveyConfig",
    "estimate_interviews",
    "load_config",
    "parse_config",
    "segment_sizes",
    "validate_config",
]
