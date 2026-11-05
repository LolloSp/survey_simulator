"""Fixture condivise per i test della configurazione."""

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from synthsurvey.config import LoadedConfig, load_config

ESEMPI_DIR = Path(__file__).resolve().parents[2] / "configs" / "examples"
ESEMPI = sorted(ESEMPI_DIR.glob("*.yaml"))


def config_base() -> dict[str, Any]:
    """Configurazione minima valida, replicata in memoria per poterla alterare."""
    return {
        "project": {"name": "test-config", "seed": 1},
        "sample": {
            "total": 100,
            "allocation": "quota",
            "segments": {
                "consumer": {
                    "share": 0.7,
                    "source": "istat_individui",
                    "filters": {"age": [18, 99], "region": "all"},
                    "quotas": ["sex", "age_band", "macro_area"],
                },
                "pmi": {
                    "share": 0.3,
                    "source": "istat_imprese",
                    "filters": {"employees": [1, 249], "sectors": "all"},
                    "quotas": ["size_class", "sector"],
                    "oversample": {"size_class": {"micro": 0.4, "piccola": 0.35, "media": 0.25}},
                    "respondent_role": ["titolare", "amministratore"],
                },
            },
        },
        "questionnaire": {"path": "questionario.yaml"},
        "modes": {"design": "within_subject", "enabled": ["cawi", "cati", "capi"]},
        "engine": {
            "models": [{"provider": "anthropic", "model": "modello-di-prova"}],
            "temperature": 0.8,
            "replicates": 3,
        },
        "run": {"pilot": False, "pilot_size": 12, "frozen": False, "budget_max_eur": 50},
        "output": {"formats": ["parquet", "csv"], "dir": "runs"},
    }


@pytest.fixture
def base() -> dict[str, Any]:
    return copy.deepcopy(config_base())


Scrivi = Callable[[dict[str, Any]], Path]
Carica = Callable[[dict[str, Any]], LoadedConfig]


@pytest.fixture
def scrivi_config(tmp_path: Path) -> Scrivi:
    """Scrive la config in una cartella temporanea insieme a un questionario vuoto."""

    def _scrivi(data: dict[str, Any]) -> Path:
        (tmp_path / "questionario.yaml").write_text("id: q\nsections: []\n", encoding="utf-8")
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        return path

    return _scrivi


@pytest.fixture
def carica(scrivi_config: Scrivi) -> Carica:
    def _carica(data: dict[str, Any]) -> LoadedConfig:
        return load_config(scrivi_config(data))

    return _carica
