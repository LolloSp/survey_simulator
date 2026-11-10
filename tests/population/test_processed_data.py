"""Integrità delle tavole in data/processed: manifest, hash, copertura, ordini di grandezza."""

from pathlib import Path

import polars as pl
import pytest

from survey_simulator.population import categories as cat
from survey_simulator.population.istat import TABLES, read_manifest, verify_manifest

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
RAW = PROCESSED.parent / "raw"


def tabella(name: str) -> pl.DataFrame:
    return pl.read_csv(PROCESSED / f"{name}.csv")


def test_manifest_presente_e_coerente() -> None:
    manifest = read_manifest(PROCESSED)
    assert manifest is not None
    assert set(manifest.tables) == set(TABLES)
    assert verify_manifest(PROCESSED, RAW) == []
    for name, spec in TABLES.items():
        entry = manifest.tables[name]
        assert entry.period == spec.period
        assert entry.columns == list(spec.columns)
        assert entry.rows == tabella(name).height
    assert "CC BY" in manifest.license["name"]


@pytest.mark.parametrize(
    "name",
    [
        "population_region_sex_age",
        "education_region_sex_ageclass",
        "employment_region_sex_ageclass",
        "firms_region_sector_size",
    ],
)
def test_tavole_regionali_coprono_tutte_le_regioni(name: str) -> None:
    df = tabella(name)
    assert sorted(df["region"].unique().to_list()) == sorted(cat.REGIONS)
    assert sorted(df["macro_area"].unique().to_list()) == sorted(cat.MACRO_AREAS)
    assert (df["count"] >= 0).all()


def test_popolazione_ordine_di_grandezza() -> None:
    df = tabella("population_region_sex_age")
    assert df.height == 20 * 2 * 101
    assert df["age"].min() == 0
    assert 55_000_000 < df["count"].sum() < 62_000_000
    assert 45_000_000 < df.filter(pl.col("age") >= 18)["count"].sum() < 55_000_000


def test_istruzione_e_condizione_complete() -> None:
    edu = tabella("education_region_sex_ageclass")
    assert sorted(edu["education"].unique().to_list()) == sorted(cat.EDUCATION)
    assert edu.height == 20 * 2 * 4 * 3
    emp = tabella("employment_region_sex_ageclass")
    assert sorted(emp["employment"].unique().to_list()) == sorted(cat.EMPLOYMENT)
    assert emp.height == 20 * 2 * 4 * 4
    assert 48_000_000 < emp["count"].sum() < 56_000_000


def test_istruzione_nazionale_completa() -> None:
    df = tabella("education_sex_ageclass_national")
    assert df.height == 2 * 6 * 3
    assert 45_000_000 < df["count"].sum() < 55_000_000


def test_occupati_nazionali_completi() -> None:
    df = tabella("employed_sex_ageclass_education_national")
    assert df.height == 2 * 6 * 3
    assert 22_000_000 < df["count"].sum() < 26_000_000
    # Gli occupati per sesso ed età non superano la popolazione corrispondente.
    pop = (
        tabella("education_sex_ageclass_national")
        .group_by(["sex", "age_class"])
        .agg(pl.col("count").sum().alias("pop"))
    )
    occ = df.group_by(["sex", "age_class"]).agg(pl.col("count").sum().alias("occ"))
    assert (
        (occ.join(pop, on=["sex", "age_class"]).select(pl.col("occ") <= pl.col("pop")))
        .to_series()
        .all()
    )


def test_imprese_ordine_di_grandezza() -> None:
    df = tabella("firms_region_sector_size")
    assert sorted(df["sector"].unique().to_list()) == sorted(cat.SECTORS)
    assert set(df["size_class"].unique().to_list()) == {*cat.SIZE_CLASSES_PMI, cat.SIZE_CLASS_LARGE}
    assert 4_000_000 < df["count"].sum() < 5_500_000


# --- coerenza fra tavole -------------------------------------------------------


def test_censimento_15_piu_coerente_con_popolazione_18_piu() -> None:
    """Per ogni regione la popolazione 15+ del censimento (31/12/2024) è poco sopra
    quella 18+ al 1/1/2025: la differenza sono i 15-17enni, circa il 3% degli adulti."""
    pop = (
        tabella("population_region_sex_age")
        .filter(pl.col("age") >= 15)
        .group_by("region")
        .agg(pl.col("count").sum())
    )
    emp = tabella("employment_region_sex_ageclass").group_by("region").agg(pl.col("count").sum())
    ratio = pop.join(emp, on="region", suffix="_emp").with_columns(
        (pl.col("count_emp") / pl.col("count")).alias("ratio")
    )
    fuori = ratio.filter((pl.col("ratio") < 0.97) | (pl.col("ratio") > 1.03))
    assert fuori.is_empty(), fuori


def test_istruzione_9_piu_coerente_con_condizione_15_piu() -> None:
    """Per ogni regione e sesso la popolazione 9+ (tavola istruzione) supera la 15+
    (tavola condizione) della quota di 9-14enni, fra il 2% e il 12%."""
    edu = (
        tabella("education_region_sex_ageclass")
        .group_by(["region", "sex"])
        .agg(pl.col("count").sum())
    )
    emp = (
        tabella("employment_region_sex_ageclass")
        .group_by(["region", "sex"])
        .agg(pl.col("count").sum())
    )
    ratio = edu.join(emp, on=["region", "sex"], suffix="_emp").with_columns(
        (pl.col("count") / pl.col("count_emp")).alias("ratio")
    )
    fuori = ratio.filter((pl.col("ratio") < 1.02) | (pl.col("ratio") > 1.12))
    assert fuori.is_empty(), fuori


def test_forze_di_lavoro_nazionali_coerenti_con_censimento() -> None:
    """Il totale 15+ delle Forze di lavoro (fino a 89 anni, popolazione in famiglia)
    sta entro pochi punti dal totale 15+ del censimento, per sesso."""
    nat = tabella("education_sex_ageclass_national").group_by("sex").agg(pl.col("count").sum())
    emp = tabella("employment_region_sex_ageclass").group_by("sex").agg(pl.col("count").sum())
    ratio = nat.join(emp, on="sex", suffix="_emp").with_columns(
        (pl.col("count") / pl.col("count_emp")).alias("ratio")
    )
    fuori = ratio.filter((pl.col("ratio") < 0.93) | (pl.col("ratio") > 1.02))
    assert fuori.is_empty(), fuori


def test_imprese_per_macro_area_proporzionate_alla_popolazione() -> None:
    """Imprese per 1000 adulti (18+) per macro-area: fra 60 e 130 ovunque (dato ISTAT ~95)."""
    pop = (
        tabella("population_region_sex_age")
        .filter(pl.col("age") >= 18)
        .group_by("macro_area")
        .agg(pl.col("count").sum())
    )
    firms = tabella("firms_region_sector_size").group_by("macro_area").agg(pl.col("count").sum())
    ratio = pop.join(firms, on="macro_area", suffix="_firms").with_columns(
        (pl.col("count_firms") / pl.col("count") * 1000).alias("per_mille")
    )
    fuori = ratio.filter((pl.col("per_mille") < 60) | (pl.col("per_mille") > 130))
    assert fuori.is_empty(), fuori


# --- tavole per le persone (M4) ---------------------------------------------


@pytest.mark.parametrize(
    ("name", "categorie"),
    [
        ("trust_sex_ageclass_education", ["diffida", "si_fida"]),
        ("internet_sex_ageclass_education", ["mai", "occasionale", "quotidiano"]),
        (
            "political_info_sex_ageclass_education",
            ["mai", "quotidiana", "saltuaria", "settimanale"],
        ),
        ("religion_sex_ageclass_education", ["mai", "saltuaria", "settimanale"]),
    ],
)
def test_atteggiamenti_completi(name: str, categorie: list[str]) -> None:
    df = tabella(name)
    assert sorted(df["category"].unique().to_list()) == categorie
    assert sorted(df["education"].unique().to_list()) == sorted(cat.EDUCATION)
    assert df["age_class"].n_unique() == 4
    assert df.height == 2 * 4 * 3 * len(categorie)
    assert (df["count"] >= 0).all()
    # Ogni cella demografica ha almeno una categoria con persone.
    per_cella = df.group_by(["sex", "age_class", "education"]).agg(pl.col("count").sum())
    assert (per_cella["count"] > 0).all()


def test_soddisfazione_completa() -> None:
    df = tabella("life_satisfaction_sex_ageclass_education")
    assert df.height == 2 * 4 * 3 * 11
    media = (df["category"].cast(pl.Float64) * df["count"]).sum() / df["count"].sum()
    assert 6.5 < media < 8.0


def test_giudizio_economico_e_quintili_regionali() -> None:
    ej = tabella("economic_judgement_region")
    assert sorted(ej["region"].unique().to_list()) == sorted(cat.REGIONS)
    assert ej.height == 20 * 4
    ir = tabella("income_quintile_region")
    assert sorted(ir["region"].unique().to_list()) == sorted(cat.REGIONS)
    somme = ir.group_by("region").agg(pl.col("share").sum())
    assert ((somme["share"] - 1).abs() < 0.02).all()


def test_quintili_principale_percettore() -> None:
    df = tabella("income_quintile_main_earner")
    assert df.height == 9 * 5
    assert sorted(df["dimension"].unique().to_list()) == ["education", "employment"]


def test_tavole_imprese_censimento() -> None:
    rel = tabella("firm_relations_sector_size")
    assert rel.height == 6 * 3
    assert (rel["with_relations"] <= rel["total"]).all()
    obj = tabella("firm_objectives_sector_size")
    assert obj.height == 6 * 2 * 6
    assert (obj["pursued"] <= obj["total"]).all()
