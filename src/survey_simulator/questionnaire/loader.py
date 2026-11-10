"""Caricamento e validazione del questionario YAML, anche rispetto alla configurazione."""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from survey_simulator.config.schema import SurveySimulatorConfig
from survey_simulator.questionnaire.routing import validate_show_if
from survey_simulator.questionnaire.schema import Questionnaire


class QuestionnaireError(Exception):
    """Questionario non valido: raccoglie tutti i problemi trovati."""

    def __init__(self, path: Path, issues: list[str]) -> None:
        self.path = path
        self.issues = issues
        super().__init__(self.__str__())

    def __str__(self) -> str:
        righe = [f"Questionario non valido: {self.path}"]
        righe.extend(f"  - {i}" for i in self.issues)
        return "\n".join(righe)


@dataclass(frozen=True)
class LoadedQuestionnaire:
    path: Path
    questionnaire: Questionnaire
    sha256: str
    warnings: list[str] = field(default_factory=list)


def _issues_from_validation_error(exc: ValidationError) -> list[str]:
    out: list[str] = []
    for err in exc.errors(include_url=False):
        loc = ".".join(str(p) for p in err["loc"]) or "<radice>"
        out.append(f"{loc}: {err['msg'].removeprefix('Value error, ')}")
    return out


def parse_questionnaire(raw: dict[str, Any], path: Path = Path("<memoria>")) -> Questionnaire:
    try:
        q = Questionnaire.model_validate(raw)
    except ValidationError as exc:
        raise QuestionnaireError(path, _issues_from_validation_error(exc)) from exc
    errori = validate_show_if(q)
    if errori:
        raise QuestionnaireError(path, errori)
    return q


def check_against_config(q: Questionnaire, config: SurveySimulatorConfig) -> list[str]:
    """Errori di coerenza con la configurazione: segmenti citati che non esistono."""
    segmenti = set(config.sample.segments)
    ignoti = sorted(q.segments() - segmenti)
    if ignoti:
        return [
            f"applies_to cita segmenti assenti nella config: {', '.join(ignoti)} "
            f"(disponibili: {', '.join(sorted(segmenti))})"
        ]
    return []


def load_questionnaire(
    path: Path | str, config: SurveySimulatorConfig | None = None
) -> LoadedQuestionnaire:
    """Legge e valida il questionario; con `config` controlla anche i segmenti."""
    path = Path(path)
    if not path.is_file():
        raise QuestionnaireError(path, ["file non trovato"])
    data = path.read_bytes()
    try:
        raw = yaml.safe_load(data.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise QuestionnaireError(path, [f"YAML malformato: {exc}"]) from exc
    if not isinstance(raw, dict):
        raise QuestionnaireError(path, ["il file deve contenere una mappa"])
    q = parse_questionnaire(raw, path)
    warnings: list[str] = []
    if config is not None:
        errori = check_against_config(q, config)
        if errori:
            raise QuestionnaireError(path, errori)
        for seg in config.sample.segments:
            if not any(qq.applies_to is None or seg in qq.applies_to for qq in q.questions):
                warnings.append(f"nessuna domanda si applica al segmento {seg}")
    return LoadedQuestionnaire(
        path=path, questionnaire=q, sha256=hashlib.sha256(data).hexdigest(), warnings=warnings
    )
