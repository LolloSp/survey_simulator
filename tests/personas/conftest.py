"""Fixture per le persone: tavole, campione e priori di default."""

from pathlib import Path

import pytest

from survey_simulator.config import SurveySimulatorConfig, load_config
from survey_simulator.personas import Names, Priors, load_names, load_priors
from survey_simulator.population.sample import SampleResult, build_sample
from survey_simulator.population.tables import IstatTables, load_tables
from tests.config.conftest import ESEMPI_DIR

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"


@pytest.fixture(scope="session")
def tables() -> IstatTables:
    return load_tables(PROCESSED)


@pytest.fixture(scope="session")
def priors() -> Priors:
    return load_priors()


@pytest.fixture(scope="session")
def names() -> Names:
    return load_names()


@pytest.fixture(scope="session")
def config_100() -> SurveySimulatorConfig:
    return load_config(ESEMPI_DIR / "mercato_100.yaml").config


@pytest.fixture(scope="session")
def sample_100(config_100: SurveySimulatorConfig, tables: IstatTables) -> SampleResult:
    return build_sample(config_100, PROCESSED, tables=tables)
