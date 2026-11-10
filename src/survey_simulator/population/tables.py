"""Caricamento delle tavole ISTAT normalizzate (data/processed) per la generazione."""

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from survey_simulator.population.istat.manifest import read_manifest
from survey_simulator.population.istat.tables import TABLES


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
    # Tavole per le persone (M4)
    trust: pl.DataFrame  # sex, age_class, education, category, count
    life_satisfaction: pl.DataFrame
    internet: pl.DataFrame
    political_info: pl.DataFrame
    religion: pl.DataFrame
    economic_judgement: pl.DataFrame  # ..., category, count (per regione)
    income_main_earner: pl.DataFrame  # dimension, code, category, quintile, share
    income_region: pl.DataFrame  # ..., quintile, share
    firm_relations: pl.DataFrame  # sector, size_class, total, with_relations
    firm_objectives: pl.DataFrame  # sector, size_class, objective, total, pursued


_FIELDS = {
    "population": "population_region_sex_age",
    "education": "education_region_sex_ageclass",
    "employment": "employment_region_sex_ageclass",
    "education_national": "education_sex_ageclass_national",
    "employed_national": "employed_sex_ageclass_education_national",
    "firms": "firms_region_sector_size",
    "trust": "trust_sex_ageclass_education",
    "life_satisfaction": "life_satisfaction_sex_ageclass_education",
    "internet": "internet_sex_ageclass_education",
    "political_info": "political_info_sex_ageclass_education",
    "religion": "religion_sex_ageclass_education",
    "economic_judgement": "economic_judgement_region",
    "income_main_earner": "income_quintile_main_earner",
    "income_region": "income_quintile_region",
    "firm_relations": "firm_relations_sector_size",
    "firm_objectives": "firm_objectives_sector_size",
}


def load_tables(processed_dir: Path) -> IstatTables:
    """Legge le sei tavole; richiede il manifest e verifica che le colonne siano quelle attese."""
    processed_dir = Path(processed_dir)
    manifest = read_manifest(processed_dir)
    if manifest is None:
        raise TablesError(
            f"manifest non trovato in {processed_dir}: eseguire `survey-simulator data fetch`"
        )
    frames: dict[str, pl.DataFrame] = {}
    for field, name in _FIELDS.items():
        if name not in manifest.tables:
            raise TablesError(
                f"tavola {name} assente dal manifest: eseguire `survey-simulator data fetch`"
            )
        path = processed_dir / manifest.tables[name].file
        if not path.is_file():
            raise TablesError(f"file {path} mancante")
        df = pl.read_csv(path)
        attese = list(TABLES[name].columns)
        if df.columns != attese:
            raise TablesError(f"{name}: colonne {df.columns} diverse da {attese}")
        if "count" in df.columns:
            df = df.with_columns(pl.col("count").cast(pl.Float64))
        if "quintile" in df.columns:
            df = df.with_columns(pl.col("quintile").cast(pl.String))
        frames[field] = df
    return IstatTables(**frames)
