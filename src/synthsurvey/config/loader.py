"""Caricamento e validazione del file di configurazione YAML."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from synthsurvey.config.rules import Issue, Level, apply_rules
from synthsurvey.config.schema import SynthSurveyConfig


class ConfigError(Exception):
    """Configurazione non valida: raccoglie tutti i problemi trovati."""

    def __init__(self, path: Path, issues: list[Issue]) -> None:
        self.path = path
        self.issues = issues
        super().__init__(self.__str__())

    def __str__(self) -> str:
        righe = [f"Configurazione non valida: {self.path}"]
        righe.extend(f"  - {i.location}: {i.message}" for i in self.issues)
        return "\n".join(righe)


@dataclass(frozen=True)
class LoadedConfig:
    path: Path
    config: SynthSurveyConfig
    warnings: list[Issue] = field(default_factory=list)


def _issues_from_validation_error(exc: ValidationError) -> list[Issue]:
    issues: list[Issue] = []
    for err in exc.errors(include_url=False):
        loc = ".".join(str(p) for p in err["loc"]) or "<radice>"
        msg = err["msg"]
        # I ValueError sollevati dai validatori arrivano con il prefisso inglese.
        prefisso = "Value error, "
        msg = msg.removeprefix(prefisso)
        issues.append(Issue(Level.ERROR, loc, msg))
    return issues


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(path, [Issue(Level.ERROR, "<file>", "file non trovato")])
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(path, [Issue(Level.ERROR, "<yaml>", f"YAML malformato: {exc}")]) from exc
    if not isinstance(raw, dict):
        raise ConfigError(
            path, [Issue(Level.ERROR, "<radice>", "il file deve contenere una mappa di sezioni")]
        )
    return raw


def _resolve_paths(config: SynthSurveyConfig, base_dir: Path) -> SynthSurveyConfig:
    """Rende assoluti i percorsi relativi, rispetto alla cartella del file di config."""

    def assoluto(p: Path) -> Path:
        return p if p.is_absolute() else (base_dir / p).resolve()

    questionnaire = config.questionnaire.model_copy(
        update={"path": assoluto(config.questionnaire.path)}
    )
    output = config.output.model_copy(update={"dir": assoluto(config.output.dir)})
    personas = config.personas
    if personas.priors_path is not None:
        personas = personas.model_copy(update={"priors_path": assoluto(personas.priors_path)})
    engine = config.engine
    if engine.cache_dir is not None:
        engine = engine.model_copy(update={"cache_dir": assoluto(engine.cache_dir)})
    return config.model_copy(
        update={
            "questionnaire": questionnaire,
            "output": output,
            "personas": personas,
            "engine": engine,
        }
    )


def parse_config(raw: dict[str, Any], path: Path = Path("<memoria>")) -> SynthSurveyConfig:
    """Valida un dizionario già letto; solleva ConfigError con tutti gli errori di schema."""
    try:
        return SynthSurveyConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(path, _issues_from_validation_error(exc)) from exc


def validate_config(config: SynthSurveyConfig, path: Path = Path("<memoria>")) -> list[Issue]:
    """Applica le regole incrociate: solleva ConfigError sugli errori, restituisce gli avvisi."""
    issues = apply_rules(config)
    if config.questionnaire.path.is_absolute() and not config.questionnaire.path.is_file():
        issues.append(
            Issue(
                Level.ERROR,
                "questionnaire.path",
                f"file non trovato: {config.questionnaire.path}",
            )
        )
    priors = config.personas.priors_path
    if priors is not None and priors.is_absolute() and not priors.is_file():
        issues.append(Issue(Level.ERROR, "personas.priors_path", f"file non trovato: {priors}"))
    errori = [i for i in issues if i.level is Level.ERROR]
    if errori:
        raise ConfigError(path, errori)
    return [i for i in issues if i.level is Level.WARNING]


def load_config(path: Path | str) -> LoadedConfig:
    """Legge, valida e normalizza un file di configurazione.

    Solleva ConfigError se il file manca, lo YAML è malformato, lo schema non
    è rispettato o una regola incrociata fallisce. Gli avvisi non bloccano e
    sono restituiti in `LoadedConfig.warnings`.
    """
    path = Path(path)
    raw = _read_yaml(path)
    config = parse_config(raw, path)
    config = _resolve_paths(config, path.parent.resolve())
    warnings = validate_config(config, path)
    return LoadedConfig(path=path, config=config, warnings=warnings)
