"""Fixture: questionario di esempio e dizionario base modificabile."""

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from survey_simulator.questionnaire import Questionnaire, load_questionnaire

ESEMPIO = Path(__file__).resolve().parents[2] / "questionnaires" / "examples" / "mercato_v1.yaml"


@pytest.fixture(scope="session")
def esempio() -> Questionnaire:
    return load_questionnaire(ESEMPIO).questionnaire


@pytest.fixture(scope="session")
def raw_esempio() -> dict[str, Any]:
    return yaml.safe_load(ESEMPIO.read_text(encoding="utf-8"))


@pytest.fixture
def raw(raw_esempio: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(raw_esempio)


def domanda(raw: dict[str, Any], qid: str) -> dict[str, Any]:
    for s in raw["sections"]:
        for q in s["questions"]:
            if q["id"] == qid:
                return q
    raise KeyError(qid)
