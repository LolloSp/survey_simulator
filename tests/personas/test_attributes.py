"""Estrazione degli attributi: distribuzioni condizionate, reddito, Beta, nomi, imprese."""

from collections import Counter

import numpy as np
import polars as pl
import pytest

from survey_simulator.personas import Names, Priors
from survey_simulator.personas.attributes import (
    AttributeSampler,
    ProfileError,
    avq_age_class,
    lfs_age_class,
)
from survey_simulator.personas.schema import BetaPrior
from survey_simulator.population.tables import IstatTables


@pytest.fixture(scope="module")
def sampler(tables: IstatTables, priors: Priors, names: Names) -> AttributeSampler:
    return AttributeSampler(tables, priors, names)


def test_classi_di_eta() -> None:
    assert avq_age_class(18, young="14_24") == "14_24"
    assert avq_age_class(24, young="6_24") == "6_24"
    assert avq_age_class(25, young="14_24") == "25_44"
    assert avq_age_class(64, young="14_24") == "45_64"
    assert avq_age_class(90, young="14_24") == "65_plus"
    assert lfs_age_class(18) == "15_24"
    assert lfs_age_class(54) == "45_54"
    assert lfs_age_class(70) == "65_89"


def test_attributo_avq_segue_la_tavola(sampler: AttributeSampler, tables: IstatTables) -> None:
    """Su 20.000 estrazioni la quota di chi si fida coincide con ISTAT entro 1,5 punti."""
    rng = np.random.default_rng(1)
    esiti = Counter(sampler.avq("trust", "f", 40, "laurea_o_oltre", rng) for _ in range(20_000))
    quota = esiti["si_fida"] / 20_000
    riga = tables.trust.filter(
        (pl.col("sex") == "f")
        & (pl.col("age_class") == "25_44")
        & (pl.col("education") == "laurea_o_oltre")
    )
    attesa = riga.filter(pl.col("category") == "si_fida")["count"].item() / riga["count"].sum()
    assert abs(quota - attesa) < 0.015


def test_soddisfazione_distribuzione(sampler: AttributeSampler) -> None:
    rng = np.random.default_rng(2)
    valori = [int(sampler.avq("life_satisfaction", "m", 30, "diploma", rng)) for _ in range(5_000)]
    assert min(valori) >= 0 and max(valori) <= 10
    assert 6.5 < float(np.mean(valori)) < 8.2


def test_giudizio_economico_regionale(sampler: AttributeSampler) -> None:
    rng = np.random.default_rng(3)
    esiti = Counter(sampler.economic_judgement("calabria", rng) for _ in range(5_000))
    assert set(esiti) <= {"ottime", "adeguate", "scarse", "insufficienti"}
    assert esiti["scarse"] + esiti["insufficienti"] > 0.3 * 5_000
    with pytest.raises(ProfileError, match="regione"):
        sampler.economic_judgement("atlantide", rng)


def test_reddito_combina_le_tre_dimensioni(sampler: AttributeSampler) -> None:
    rng = np.random.default_rng(4)
    n = 10_000
    laureati = np.array(
        [sampler.income_quintile("laurea_o_oltre", "occupato", "lombardia", rng) for _ in range(n)]
    )
    bassi = np.array(
        [sampler.income_quintile("fino_media", "in_cerca", "calabria", rng) for _ in range(n)]
    )
    assert laureati.mean() > bassi.mean() + 1.5
    assert (laureati == 5).mean() > 0.4
    assert (bassi == 1).mean() > 0.4
    assert set(np.unique(laureati)) <= {1, 2, 3, 4, 5}


def test_beta_rispetta_media_e_modificatori(sampler: AttributeSampler) -> None:
    prior = BetaPrior(base=0.5, concentration=20, modifiers={"education": {"laurea_o_oltre": 0.2}})
    rng = np.random.default_rng(5)
    base = np.mean([sampler.beta(prior, {"education": "diploma"}, rng) for _ in range(5_000)])
    alto = np.mean(
        [sampler.beta(prior, {"education": "laurea_o_oltre"}, rng) for _ in range(5_000)]
    )
    assert abs(base - 0.5) < 0.02
    assert abs(alto - 0.7) < 0.02
    estremo = BetaPrior(base=0.9, concentration=5, modifiers={"x": {"a": 0.5}})
    valori = [sampler.beta(estremo, {"x": "a"}, rng) for _ in range(1_000)]
    assert max(valori) <= 1.0 and float(np.mean(valori)) < 0.97, "media troncata a 0.95"


def test_nomi_per_sesso_e_coorte(sampler: AttributeSampler, names: Names) -> None:
    rng = np.random.default_rng(6)
    assert sampler.name_for("f", 20, rng) in names.f[2000]
    assert sampler.name_for("m", 80, rng) in names.m[1940]
    assert sampler.name_for("f", 45, rng) in names.f[1980]


def test_individuo_completo(sampler: AttributeSampler) -> None:
    unit = {
        "unit_id": "consumer_00001",
        "segment": "consumer",
        "source": "istat_individui",
        "region": "veneto",
        "macro_area": "nord_est",
        "sex": "f",
        "age": 37,
        "age_band": "35_44",
        "education": "diploma",
        "employment": "occupato",
    }
    attrs, prov = sampler.individual(unit, np.random.default_rng(7))
    assert set(attrs) >= {
        "income_quintile",
        "economic_judgement",
        "trust",
        "internet",
        "political_info",
        "religion",
        "life_satisfaction",
        "sensibilita_prezzo",
        "acquiescenza",
    }
    assert (
        prov["trust"] == "istat"
        and prov["sensibilita_prezzo"] == "ipotesi"
        and prov["age"] == "campione"
    )
    assert 0 <= attrs["acquiescenza"] <= 1


def test_impresa_completa(sampler: AttributeSampler) -> None:
    unit = {
        "unit_id": "pmi_00001",
        "segment": "pmi",
        "source": "istat_imprese",
        "region": "lazio",
        "macro_area": "centro",
        "sector": "commercio",
        "size_class": "micro",
    }
    rng = np.random.default_rng(8)
    attrs, prov = sampler.firm(unit, ["titolare", "amministratore"], rng)
    assert attrs["respondent_role"] in {"titolare", "amministratore"}
    assert 1 <= attrs["employees"] <= 9
    assert attrs["sex"] in {"m", "f"} and 30 <= attrs["age"] <= 70
    assert attrs["education"] in {"fino_media", "diploma", "laurea_o_oltre"}
    assert prov["objectives"] == "istat_proxy", "per le microimprese gli obiettivi sono un proxy"
    assert prov["with_relations"] == "istat"
    media = sampler.firm({**unit, "size_class": "media"}, None, rng)[0]
    assert 50 <= media["employees"] <= 249
    with pytest.raises(ProfileError, match="ruolo"):
        sampler.firm(unit, ["ruolo_inesistente"], rng)


def test_ruoli_seguono_le_quote(sampler: AttributeSampler, priors: Priors) -> None:
    unit = {
        "region": "lazio",
        "macro_area": "centro",
        "sector": "industria",
        "size_class": "media",
        "source": "istat_imprese",
    }
    rng = np.random.default_rng(9)
    esiti = Counter(sampler.firm(unit, None, rng)[0]["respondent_role"] for _ in range(4_000))
    for ruolo, quota in priors.respondent_roles["media"].items():
        assert abs(esiti[ruolo] / 4_000 - quota) < 0.03
