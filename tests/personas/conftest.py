"""Fixture per le persone: tavole, campione e priori di default."""

from pathlib import Path

import pytest

from synthsurvey.config import SynthSurveyConfig, load_config
from synthsurvey.personas import Names, Priors, load_names, load_priors
from synthsurvey.population.sample import SampleResult, build_sample
from synthsurvey.population.tables import IstatTables, load_tables
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
def config_100() -> SynthSurveyConfig:
    return load_config(ESEMPI_DIR / "mercato_100.yaml").config


@pytest.fixture(scope="session")
def sample_100(config_100: SynthSurveyConfig, tables: IstatTables) -> SampleResult:
    return build_sample(config_100, PROCESSED, tables=tables)
