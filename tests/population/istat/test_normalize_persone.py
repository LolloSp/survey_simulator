"""Normalizzazione delle tavole per le persone su estratti reali (Italia, Piemonte, Sardegna)."""

import polars as pl
import pytest

from survey_simulator.population import categories as cat
from survey_simulator.population.istat import codelists_persone as cp
from survey_simulator.population.istat import normalize_persone as npz
from survey_simulator.population.istat.normalize import NormalizeError
from tests.population.conftest import REGIONI_FIXTURE, fixture_text

TRUST = "83_63_DF_DCCV_AVQ_PERSONE_124"
SAT = "83_63_DF_DCCV_AVQ_PERSONE_138"
INTERNET = "83_63_DF_DCCV_AVQ_PERSONE_236"
POLITICS = "83_63_DF_DCCV_AVQ_PERSONE_109"
RELIGION = "83_63_DF_DCCV_AVQ_PERSONE_134"
ECON = "82_87_DF_DCCV_AVQ_FAMIGLIE_14"
INCOME = "32_38_DF_DCCV_QUINTOREDD_5"
INCOME_REG = "32_38_DF_DCCV_QUINTOREDD_6"
RELATIONS = "742_1106_DF_DCSI_CPI_RELAZIONI_6"
OBJECTIVES = "742_1102_DF_DCSI_CPI_CONTROLLO_22"

KEYS = ["sex", "age_class", "education"]


def quote(df: pl.DataFrame, keys: list[str]) -> pl.DataFrame:
    return df.with_columns((pl.col("count") / pl.col("count").sum().over(keys)).alias("share"))


def test_fiducia() -> None:
    df = npz.trust_sex_ageclass_education([fixture_text(TRUST)], "2024")
    assert df.columns == [*KEYS, "category", "count"]
    assert df.height == 2 * 4 * 3 * 2
    assert sorted(df["education"].unique().to_list()) == sorted(cat.EDUCATION)
    assert sorted(df["age_class"].unique().to_list()) == ["14_24", "25_44", "45_64", "65_plus"]
    q = quote(df, KEYS)
    laureati = q.filter(
        (pl.col("education") == "laurea_o_oltre") & (pl.col("category") == "si_fida")
    )
    bassi = q.filter((pl.col("education") == "fino_media") & (pl.col("category") == "si_fida"))
    assert laureati["share"].mean() > bassi["share"].mean(), "la fiducia cresce con l'istruzione"


def test_soddisfazione() -> None:
    df = npz.life_satisfaction_sex_ageclass_education([fixture_text(SAT)], "2024")
    assert df.height == 2 * 4 * 3 * 11
    assert sorted(int(c) for c in df["category"].unique().to_list()) == list(range(11))
    media = (df["category"].cast(pl.Float64) * df["count"]).sum() / df["count"].sum()
    assert 6.5 < media < 8.0


def test_internet() -> None:
    df = npz.internet_sex_ageclass_education([fixture_text(INTERNET)], "2024")
    assert sorted(df["category"].unique().to_list()) == ["mai", "occasionale", "quotidiano"]
    q = quote(df, KEYS)
    giovani = q.filter((pl.col("age_class") == "25_44") & (pl.col("category") == "mai"))[
        "share"
    ].mean()
    anziani = q.filter((pl.col("age_class") == "65_plus") & (pl.col("category") == "mai"))[
        "share"
    ].mean()
    assert anziani > 3 * giovani


def test_informazione_politica() -> None:
    df = npz.political_info_sex_ageclass_education([fixture_text(POLITICS)], "2024")
    assert sorted(df["category"].unique().to_list()) == [
        "mai",
        "quotidiana",
        "saltuaria",
        "settimanale",
    ]
    assert df.height == 2 * 4 * 3 * 4


def test_pratica_religiosa_con_residuo() -> None:
    df = npz.religion_sex_ageclass_education(
        [fixture_text(RELIGION), fixture_text(INTERNET)], "2024"
    )
    assert sorted(df["category"].unique().to_list()) == ["mai", "saltuaria", "settimanale"]
    assert (df["count"] >= 0).all()
    q = quote(df, KEYS)
    assert q.filter(pl.col("category") == "saltuaria")["share"].mean() > 0.2


def test_ordine_dei_testi_religione() -> None:
    with pytest.raises(NormalizeError, match="pratica religiosa"):
        npz.religion_sex_ageclass_education(
            [fixture_text(INTERNET), fixture_text(RELIGION)], "2024"
        )


def test_giudizio_economico_regionale() -> None:
    df = npz.economic_judgement_region(
        [fixture_text(ECON)], "2024", required_regions=REGIONI_FIXTURE
    )
    assert df.columns == ["region_code", "region", "macro_area", "category", "count"]
    assert sorted(df["category"].unique().to_list()) == sorted(cp.ECONOMIC_JUDGEMENT_AVQ.values())
    q = quote(df, ["region_code"])
    somme = q.group_by("region_code").agg(pl.col("share").sum())
    assert ((somme["share"] - 1).abs() < 1e-9).all()
    assert q.filter(pl.col("category") == "adeguate")["share"].mean() > 0.5


def test_quintili_principale_percettore() -> None:
    df = npz.income_quintile_main_earner([fixture_text(INCOME)], "2024")
    assert df.columns == ["dimension", "code", "category", "quintile", "share"]
    assert df.height == (4 + 5) * 5
    somme = df.group_by(["dimension", "code"]).agg(pl.col("share").sum())
    assert ((somme["share"] - 1).abs() < 0.02).all()
    top = df.filter(pl.col("quintile") == "5")
    assert (
        top.filter(pl.col("code") == "11")["share"].item()
        > top.filter(pl.col("code") == "3")["share"].item()
    )
    assert (
        top.filter(pl.col("code") == "2B")["share"].item()
        < top.filter(pl.col("code") == "1A")["share"].item()
    )


def test_quintili_regione_con_province_autonome() -> None:
    df = npz.income_quintile_region(
        [fixture_text(INCOME_REG)], "2024", required_regions=("ITC1", "ITG2", "ITDA")
    )
    assert sorted(df["region"].unique().to_list()) == [
        "piemonte",
        "sardegna",
        "trentino_alto_adige",
    ]
    assert df.height == 3 * 5
    somme = df.group_by("region").agg(pl.col("share").sum())
    assert ((somme["share"] - 1).abs() < 0.02).all()
    q1 = df.filter(pl.col("quintile") == "1")
    assert (
        q1.filter(pl.col("region") == "sardegna")["share"].item()
        > q1.filter(pl.col("region") == "piemonte")["share"].item()
    )


def test_relazioni_imprese() -> None:
    df = npz.firm_relations_sector_size([fixture_text(RELATIONS)], "2022")
    assert df.columns == ["sector", "size_class", "total", "with_relations"]
    assert sorted(df["sector"].unique().to_list()) == sorted(cat.SECTORS)
    assert sorted(df["size_class"].unique().to_list()) == ["media", "micro", "piccola"]
    assert (df["with_relations"] <= df["total"]).all()


def test_obiettivi_imprese() -> None:
    df = npz.firm_objectives_sector_size([fixture_text(OBJECTIVES)], "2022")
    assert df.columns == ["sector", "size_class", "objective", "total", "pursued"]
    assert sorted(df["size_class"].unique().to_list()) == ["media", "piccola"]
    assert sorted(df["objective"].unique().to_list()) == sorted(cp.FIRM_OBJECTIVES.values())
    assert (df["pursued"] <= df["total"]).all()
    tech = df.filter(pl.col("objective") == "nuove_tecnologie").with_columns(
        (pl.col("pursued") / pl.col("total")).alias("share")
    )
    assert (
        tech.filter(pl.col("size_class") == "media")["share"].mean()
        > tech.filter(pl.col("size_class") == "piccola")["share"].mean()
    )
