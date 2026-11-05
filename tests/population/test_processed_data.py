"""Integrità delle tavole in data/processed: manifest, hash, copertura, ordini di grandezza."""

from pathlib import Path

import polars as pl
import pytest

from synthsurvey.population import categories as cat
from synthsurvey.population.istat import TABLES, read_manifest, verify_manifest

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
    assert df.height == 20 * 2 * 83
    assert 45_000_000 < df["count"].sum() < 55_000_000


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


def test_imprese_ordine_di_grandezza() -> None:
    df = tabella("firms_region_sector_size")
    assert sorted(df["sector"].unique().to_list()) == sorted(cat.SECTORS)
    assert set(df["size_class"].unique().to_list()) == {*cat.SIZE_CLASSES_PMI, cat.SIZE_CLASS_LARGE}
    assert 4_000_000 < df["count"].sum() < 5_500_000
