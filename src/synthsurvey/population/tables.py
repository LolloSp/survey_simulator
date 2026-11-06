"""Caricamento delle tavole ISTAT normalizzate (data/processed) per la generazione."""

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from synthsurvey.population.istat.manifest import read_manifest
from synthsurvey.population.istat.tables import TABLES


class TablesError(FileNotFoundError):
    """Tavole normalizzate mancanti o incoerenti con il manifest."""


@dataclass(frozen=True)
class IstatTables:
    population: pl.DataFrame  # region_code, region, macro_area, sex, age, count
    education: pl.DataFrame  # ..., sex, age_class, education, count
    employment: pl.DataFrame  # ..., sex, age_class, employment, count
    education_national: pl.DataFrame  # sex, age_class, education, count
    employed_national: pl.DataFrame  # sex, age_class, education, count
    firms: pl.DataFrame  # ..., sector, size_class, count


_FIELDS = {
    "population": "population_region_sex_age",
    "education": "education_region_sex_ageclass",
    "employment": "employment_region_sex_ageclass",
    "education_national": "education_sex_ageclass_national",
    "employed_national": "employed_sex_ageclass_education_national",
    "firms": "firms_region_sector_size",
}


def load_tables(processed_dir: Path) -> IstatTables:
    """Legge le sei tavole; richiede il manifest e verifica che le colonne siano quelle attese."""
    processed_dir = Path(processed_dir)
    manifest = read_manifest(processed_dir)
    if manifest is None:
        raise TablesError(
            f"manifest non trovato in {processed_dir}: eseguire `synthsurvey data fetch`"
        )
    frames: dict[str, pl.DataFrame] = {}
    for field, name in _FIELDS.items():
        if name not in manifest.tables:
            raise TablesError(
                f"tavola {name} assente dal manifest: eseguire `synthsurvey data fetch`"
            )
        path = processed_dir / manifest.tables[name].file
        if not path.is_file():
            raise TablesError(f"file {path} mancante")
        df = pl.read_csv(path)
        attese = list(TABLES[name].columns)
        if df.columns != attese:
            raise TablesError(f"{name}: colonne {df.columns} diverse da {attese}")
        frames[field] = df.with_columns(pl.col("count").cast(pl.Float64))
    return IstatTables(**frames)
