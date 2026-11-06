"""Normalizzazione delle tavole su estratti reali (Piemonte, Sardegna, Italia)."""

import polars as pl
import pytest

from synthsurvey.population import categories as cat
from synthsurvey.population.istat import normalize as nz
from synthsurvey.population.istat.normalize import NormalizeError
from tests.population.conftest import REGIONI_FIXTURE, fixture_text

POP = "22_289_DF_DCIS_POPRES1_1"
EDU = "DF_DCSS_ISTR_LAV_PEN_2_TV_1"
EMP = "DF_DCSS_ISTR_LAV_PEN_2_TV_3"
FOR = "150_908_DF_DCCV_FORZLV1_2"
INAC = "152_928_DF_DCCV_INATTIV1_2"
ASIA = "183_277_DF_DICA_ASIAUE1P_5"
EMPLOYED = "150_938_DF_DCCV_OCCUPATIT1_2"


def test_lettura_csv_sdmx_richiede_intestazione() -> None:
    with pytest.raises(NormalizeError, match="intestazione"):
        nz.read_sdmx_csv("a,b\n1,2\n")


def test_popolazione() -> None:
    df = nz.population_region_sex_age([fixture_text(POP)], "2025", required_regions=REGIONI_FIXTURE)
    assert df.columns == ["region_code", "region", "macro_area", "sex", "age", "count"]
    assert df["region"].unique().sort().to_list() == ["piemonte", "sardegna"]
    assert df["sex"].unique().sort().to_list() == ["f", "m"]
    assert df["age"].min() == 0
    assert df["age"].max() == 100
    assert df.height == 2 * 2 * 101
    assert df["count"].dtype == pl.Int64
    # Valore letto dalla risposta ISTAT: maschi di 18 anni in Piemonte al 1° gennaio 2025.
    riga = df.filter(
        (pl.col("region") == "piemonte") & (pl.col("sex") == "m") & (pl.col("age") == 18)
    )
    assert riga["count"].item() == 20797
    assert df.sort(["region_code", "sex", "age"]).equals(df), "output ordinato"


def test_popolazione_regione_mancante() -> None:
    with pytest.raises(NormalizeError, match=r"regioni mancanti.*ITC4"):
        nz.population_region_sex_age([fixture_text(POP)], "2025", required_regions=("ITC1", "ITC4"))


def test_popolazione_periodo_assente() -> None:
    with pytest.raises(NormalizeError, match="nessuna riga"):
        nz.population_region_sex_age([fixture_text(POP)], "1999", required_regions=REGIONI_FIXTURE)


def test_istruzione() -> None:
    df = nz.education_region_sex_ageclass(
        [fixture_text(EDU)], "2024", required_regions=REGIONI_FIXTURE
    )
    assert df.columns == [
        "region_code",
        "region",
        "macro_area",
        "sex",
        "age_class",
        "education",
        "count",
    ]
    assert df["education"].unique().sort().to_list() == sorted(cat.EDUCATION)
    assert df["age_class"].unique().sort().to_list() == ["25_49", "50_64", "65_plus", "9_24"]
    assert df.height == 2 * 2 * 4 * 3
    assert (df["count"] > 0).all()


def test_istruzione_controllo_totale() -> None:
    testo = fixture_text(EDU)
    # Raddoppia il totale ISTAT di una combinazione: la somma delle categorie non torna più.
    righe = testo.splitlines()
    idx = next(i for i, r in enumerate(righe) if ",ITC1,RESPOP_AV,M,Y25-49,TOTAL,ALL," in r)
    campi = righe[idx].split(",")
    pos = righe[0].split(",").index("OBS_VALUE")
    campi[pos] = str(int(campi[pos]) * 2)
    righe[idx] = ",".join(campi)
    with pytest.raises(NormalizeError, match=r"istruzione.*non torna"):
        nz.education_region_sex_ageclass(
            ["\n".join(righe)], "2024", required_regions=REGIONI_FIXTURE
        )


def test_condizione_professionale() -> None:
    df = nz.employment_region_sex_ageclass(
        [fixture_text(EMP)], "2024", required_regions=REGIONI_FIXTURE
    )
    assert df["employment"].unique().sort().to_list() == sorted(cat.EMPLOYMENT)
    assert df["age_class"].unique().sort().to_list() == ["15_24", "25_49", "50_64", "65_plus"]
    assert df.height == 2 * 2 * 4 * 4
    # I pensionati stanno quasi tutti nella classe 65+.
    pens = df.filter(pl.col("employment") == "pensionato")
    over65 = pens.filter(pl.col("age_class") == "65_plus")["count"].sum()
    assert over65 > 0.8 * pens["count"].sum()


def test_istruzione_nazionale() -> None:
    df = nz.education_sex_ageclass_national([fixture_text(FOR), fixture_text(INAC)], "2024")
    assert df.columns == ["sex", "age_class", "education", "count"]
    assert df.height == 2 * 6 * 3
    assert df["age_class"].unique().sort().to_list() == sorted(
        ["15_24", "25_34", "35_44", "45_54", "55_64", "65_89"]
    )
    # Valori in migliaia riportati a persone: il totale è dell'ordine dei 50 milioni.
    assert 45_000_000 < df["count"].sum() < 55_000_000


def test_istruzione_nazionale_ordine_dei_testi() -> None:
    with pytest.raises(NormalizeError, match="nessuna riga"):
        nz.education_sex_ageclass_national([fixture_text(INAC), fixture_text(FOR)], "2024")


def test_imprese() -> None:
    df = nz.firms_region_sector_size([fixture_text(ASIA)], "2024", required_regions=REGIONI_FIXTURE)
    assert df.columns == ["region_code", "region", "macro_area", "sector", "size_class", "count"]
    assert df["sector"].unique().sort().to_list() == sorted(cat.SECTORS)
    assert set(df["size_class"].unique().to_list()) <= {*cat.SIZE_CLASSES_PMI, cat.SIZE_CLASS_LARGE}
    micro = df.filter(pl.col("size_class") == "micro")["count"].sum()
    assert micro > 0.9 * df["count"].sum(), "le microimprese sono oltre il 90% del totale"


def test_occupati_nazionali() -> None:
    df = nz.employed_sex_ageclass_education_national([fixture_text(EMPLOYED)], "2024")
    assert df.columns == ["sex", "age_class", "education", "count"]
    assert df.height == 2 * 6 * 3
    assert 22_000_000 < df["count"].sum() < 26_000_000
    # Fra i 25-34enni gli occupati laureati sono più numerosi di quelli fino alla media.
    giovani = (
        df.filter(pl.col("age_class") == "25_34").group_by("education").agg(pl.col("count").sum())
    )
    valori = dict(zip(giovani["education"].to_list(), giovani["count"].to_list(), strict=True))
    assert valori["laurea_o_oltre"] > valori["fino_media"]
