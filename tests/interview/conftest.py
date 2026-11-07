"""Fixture per le interviste: persona costruita a mano, questionario di esempio, config."""

from pathlib import Path
from typing import Any

import pytest

from synthsurvey.config import SynthSurveyConfig, parse_config
from synthsurvey.personas.schema import Attitudes, Firm, Persona, Provenance, ResponseStyle
from synthsurvey.questionnaire import Questionnaire, load_questionnaire
from tests.config.conftest import config_base

ESEMPIO = Path(__file__).resolve().parents[2] / "questionnaires" / "examples" / "mercato_v1.yaml"


def make_persona(
    persona_id: str = "p_00001",
    segment: str = "consumer",
    *,
    non_so: float = 0.2,
    loquacita: float = 0.5,
) -> Persona:
    firm = None
    source = "istat_individui"
    if segment == "pmi":
        source = "istat_imprese"
        firm = Firm(
            sector="servizi",
            size_class="micro",
            employees=5,
            respondent_role="titolare",
            with_relations=True,
            objectives=["difendere la posizione competitiva"],
        )
    return Persona(
        persona_id=persona_id,
        unit_id=f"u_{persona_id}",
        segment=segment,
        source=source,
        region="Piemonte",
        macro_area="Nord-ovest",
        sex="f",
        age=44,
        age_band="35_44",
        education="diploma",
        employment="occupato",
        income_quintile=3,
        economic_judgement="adeguate",
        firm=firm,
        attitudes=Attitudes(
            trust="si_fida",
            life_satisfaction=7,
            internet="quotidiano",
            political_info="settimanale",
            religion="saltuaria",
            sensibilita_prezzo=0.6,
            fedelta_marca=0.4,
            propensione_rischio=0.3,
            apertura_novita=0.5,
        ),
        response_style=ResponseStyle(
            acquiescenza=0.5,
            desiderabilita_sociale=0.5,
            non_so=non_so,
            tempo_disponibile=0.5,
            loquacita=loquacita,
        ),
        name="Giulia",
        narrative="Giulia ha 44 anni e vive in Piemonte. Lavora e confronta i prezzi.",
        provenance={"age": Provenance.CAMPIONE, "sensibilita_prezzo": Provenance.IPOTESI},
        weight=1.0,
        weight_pop=1000.0,
    )


@pytest.fixture(scope="session")
def questionario() -> Questionnaire:
    return load_questionnaire(ESEMPIO).questionnaire


@pytest.fixture
def config() -> SynthSurveyConfig:
    raw: dict[str, Any] = config_base()
    raw["engine"]["models"] = [{"provider": "fake", "model": "fake-1"}]
    return parse_config(raw)


@pytest.fixture
def persona() -> Persona:
    return make_persona()
