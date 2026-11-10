"""Normalizzazione delle tavole per le persone (M4): atteggiamenti, reddito, imprese."""

from collections.abc import Iterable

import polars as pl

from survey_simulator.population.istat import codelists as cl
from survey_simulator.population.istat import codelists_persone as cp
from survey_simulator.population.istat.normalize import (
    REGION_COLUMNS,
    NormalizeError,
    _finalize,
    _map,
    _obs_value,
    _require_regions,
    _with_region,
    read_sdmx_csv,
)

PERSON_KEYS = ["sex", "age_class", "education"]


def _avq_persons(text: str, period: str, mapping: dict[str, str], label: str) -> pl.DataFrame:
    """Persone (migliaia -> persone) per sesso, classe d'età, titolo e categoria del quesito.

    I codici in `mapping` vengono accorpati nelle categorie; i livelli di
    istruzione 3 e 4 si sommano in `fino_media` grazie ai valori assoluti
    (misura THV).
    """
    df = _obs_value(read_sdmx_csv(text))
    df = df.filter(
        (pl.col("REF_AREA") == "IT")
        & (pl.col("MEASURE") == "THV")
        & (pl.col("TIME_PERIOD") == period)
        & (pl.col("LABOUR_PROFESS_STATUS_B") == "99")
    )
    df = _map(df, "SEX", cl.SEX_NUMERIC, "sex")
    df = _map(df, "AGE", cp.AGE_CLASS_AVQ, "age_class")
    df = _map(df, "EDU_LEV_HIGHEST", cp.EDUCATION_AVQ, "education")
    cat = _map(df, "DATA_TYPE", mapping, "category")
    if cat.is_empty():
        raise NormalizeError(f"{label}: nessuna riga per il periodo {period}")
    out = cat.group_by([*PERSON_KEYS, "category"]).agg(
        (pl.col("value").sum() * 1000).alias("count")
    )
    return _finalize(out, [*PERSON_KEYS, "category", "count"])


def trust_sex_ageclass_education(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Fiducia interpersonale (AVQ) per sesso, classe d'età e titolo di studio."""
    return _avq_persons(texts[0], period, cp.TRUST_AVQ, "fiducia")


def life_satisfaction_sex_ageclass_education(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Soddisfazione per la vita 0-10 (AVQ) per sesso, classe d'età e titolo di studio."""
    return _avq_persons(texts[0], period, cp.LIFE_SATISFACTION_AVQ, "soddisfazione")


def internet_sex_ageclass_education(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Uso di internet per frequenza (AVQ) per sesso, classe d'età e titolo di studio."""
    return _avq_persons(texts[0], period, cp.INTERNET_AVQ, "internet")


def political_info_sex_ageclass_education(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Frequenza con cui ci si informa di politica (AVQ) per sesso, classe d'età e titolo."""
    return _avq_persons(texts[0], period, cp.POLITICAL_INFO_AVQ, "informazione politica")


def religion_sex_ageclass_education(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Frequenza di un luogo di culto (AVQ): settimanale, mai, saltuaria come residuo.

    Il totale delle persone di 6 anni e più viene dal quesito sull'uso di
    internet della stessa indagine (secondo testo), sulle stesse celle.
    """
    noti = _avq_persons(texts[0], period, cp.RELIGION_AVQ, "pratica religiosa")
    totale = _avq_persons(texts[1], period, cp.INTERNET_AVQ, "internet")
    tot = totale.group_by(PERSON_KEYS).agg(pl.col("count").sum().alias("total"))
    somma = noti.group_by(PERSON_KEYS).agg(pl.col("count").sum().alias("noti"))
    resto = (
        tot.join(somma, on=PERSON_KEYS, how="left")
        .with_columns(
            (pl.col("total") - pl.col("noti").fill_null(0)).clip(0).cast(pl.Float64).alias("count")
        )
        .with_columns(pl.lit(cp.RELIGION_RESIDUAL).alias("category"))
        .select([*PERSON_KEYS, "category", "count"])
    )
    out = pl.concat([noti.with_columns(pl.col("count").cast(pl.Float64)), resto])
    return _finalize(out, [*PERSON_KEYS, "category", "count"])


def economic_judgement_region(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Giudizio delle famiglie sulle risorse economiche (AVQ) per regione, famiglie."""
    df = _obs_value(read_sdmx_csv(texts[0]))
    df = df.filter(
        (pl.col("MEASURE") == "THV")
        & (pl.col("TIME_PERIOD") == period)
        & (pl.col("NUMBER_HOUSEHOLD_COMP") == "TOT")
    )
    df = _with_region(df)
    _require_regions(df, "giudizio economico", required_regions)
    cat = _map(df, "DATA_TYPE", cp.ECONOMIC_JUDGEMENT_AVQ, "category")
    if cat.is_empty():
        raise NormalizeError(f"giudizio economico: nessuna riga per il periodo {period}")
    out = cat.group_by([*REGION_COLUMNS, "category"]).agg(
        (pl.col("value").sum() * 1000).alias("count")
    )
    return _finalize(out, [*REGION_COLUMNS, "category", "count"])


def income_quintile_main_earner(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Quota di famiglie per quintile di reddito equivalente (EU-SILC), per titolo di studio
    oppure condizione del principale percettore."""
    df = _obs_value(read_sdmx_csv(texts[0]))
    df = df.filter(
        (pl.col("REF_AREA") == "IT")
        & (pl.col("MEASURE") == "10")
        & (pl.col("TIME_PERIOD") == period)
        & pl.col("FIFTH_EQUIV_HOUSE_INC").is_in(list(cp.INCOME_QUINTILES))
    )
    edu = _map(
        df.filter(pl.col("LABPROF_STATUS_C_MAIN_EARNER") == "99"),
        "EDU_LEV_MAIN_EARN",
        cp.EDUCATION_AVQ,
        "category",
    ).select(
        pl.lit("education").alias("dimension"),
        pl.col("EDU_LEV_MAIN_EARN").alias("code"),
        "category",
        pl.col("FIFTH_EQUIV_HOUSE_INC").alias("quintile"),
        (pl.col("value") / 100).alias("share"),
    )
    status = _map(
        df.filter(pl.col("EDU_LEV_MAIN_EARN") == "99"),
        "LABPROF_STATUS_C_MAIN_EARNER",
        cp.INCOME_STATUS_CODES,
        "category",
    ).select(
        pl.lit("employment").alias("dimension"),
        pl.col("LABPROF_STATUS_C_MAIN_EARNER").alias("code"),
        "category",
        pl.col("FIFTH_EQUIV_HOUSE_INC").alias("quintile"),
        (pl.col("value") / 100).alias("share"),
    )
    out = pl.concat([edu, status])
    if out.is_empty():
        raise NormalizeError(f"quintili di reddito: nessuna riga per il periodo {period}")
    somme = out.group_by(["dimension", "code"]).agg(pl.col("share").sum())
    if ((somme["share"] - 1.0).abs() > 0.02).any():
        raise NormalizeError("quintili di reddito: le quote non sommano a 1")
    return out.sort(["dimension", "code", "quintile"])


def income_quintile_region(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Quota di famiglie per quintile di reddito equivalente (EU-SILC) per regione."""
    df = _obs_value(read_sdmx_csv(texts[0]))
    df = df.filter(
        (pl.col("MEASURE") == "10")
        & (pl.col("TIME_PERIOD") == period)
        & pl.col("FIFTH_EQUIV_HOUSE_INC").is_in(list(cp.INCOME_QUINTILES))
    )
    # EU-SILC pubblica Bolzano e Trento separate: il Trentino-Alto Adige è la
    # media semplice delle due province (quote, non conteggi).
    df = (
        df.with_columns(
            pl.when(pl.col("REF_AREA").is_in(["ITD1", "ITD2"]))
            .then(pl.lit("ITDA"))
            .otherwise(pl.col("REF_AREA"))
            .alias("REF_AREA")
        )
        .group_by(["REF_AREA", "FIFTH_EQUIV_HOUSE_INC"])
        .agg(pl.col("value").mean())
    )
    df = _with_region(df)
    _require_regions(df, "quintili per regione", required_regions)
    out = df.select(
        *REGION_COLUMNS,
        pl.col("FIFTH_EQUIV_HOUSE_INC").alias("quintile"),
        (pl.col("value") / 100).alias("share"),
    )
    # ISTAT oscura le celle con pochi casi campionari (ad esempio il primo
    # quintile in Valle d'Aosta): un solo valore mancante per regione viene
    # ricostruito come complemento a 1.
    mancanti = out.group_by("region_code").agg(pl.col("share").null_count().alias("n_null"))
    if (mancanti["n_null"] > 1).any():
        raise NormalizeError("quintili per regione: più di un quintile mancante in una regione")
    out = out.with_columns(
        pl.when(pl.col("share").is_null())
        .then((1.0 - pl.col("share").sum().over("region_code")).clip(0.0))
        .otherwise(pl.col("share"))
        .alias("share")
    )
    return out.sort(["region_code", "quintile"])


def _census_firms(df: pl.DataFrame) -> pl.DataFrame:
    df = _map(df, "ECON_ACTIVITY_NACE_2007", cp.SECTOR_BY_SECTION, "sector")
    return _map(df, "PERS_EMPL_SIZE_CLASS", cp.SIZE_CLASS_CENSUS, "size_class")


def firm_relations_sector_size(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Imprese con 3+ addetti e imprese con relazioni con altre imprese (Censimento imprese)."""
    df = _obs_value(read_sdmx_csv(texts[0]))
    df = _census_firms(df.filter((pl.col("REF_AREA") == "IT") & (pl.col("TIME_PERIOD") == period)))
    tot = df.filter(pl.col("DATA_TYPE") == "AENTN3M")
    rel = df.filter(pl.col("DATA_TYPE") == "AENTN3M_RELAT")
    if tot.is_empty() or rel.is_empty():
        raise NormalizeError(f"relazioni imprese: nessuna riga per il periodo {period}")
    keys = ["sector", "size_class"]
    out = (
        tot.group_by(keys)
        .agg(pl.col("value").sum().alias("total"))
        .join(rel.group_by(keys).agg(pl.col("value").sum().alias("with_relations")), on=keys)
    )
    return out.select([*keys, "total", "with_relations"]).sort(keys)


def firm_objectives_sector_size(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Imprese con 10+ addetti e imprese che hanno perseguito ciascun obiettivo strategico."""
    df = _obs_value(read_sdmx_csv(texts[0]))
    df = df.filter(
        (pl.col("REF_AREA") == "IT")
        & (pl.col("TIME_PERIOD") == period)
        & (pl.col("DATA_TYPE") == "AENTN10M")
        & (pl.col("TYPE_MANAGEMENT") == "TOT")
    )
    df = _census_firms(df)
    tot = df.filter((pl.col("OBJ_STRA_PU_LAST3Y") == "ALL") & (pl.col("OBJ_STRA_RESULT") == "ALL"))
    obj = _map(
        df.filter(pl.col("OBJ_STRA_RESULT") == "OBJPURSUED"),
        "OBJ_STRA_PU_LAST3Y",
        cp.FIRM_OBJECTIVES,
        "objective",
    )
    if tot.is_empty() or obj.is_empty():
        raise NormalizeError(f"obiettivi imprese: nessuna riga per il periodo {period}")
    keys = ["sector", "size_class"]
    out = (
        obj.group_by([*keys, "objective"])
        .agg(pl.col("value").sum().alias("pursued"))
        .join(tot.group_by(keys).agg(pl.col("value").sum().alias("total")), on=keys)
    )
    return out.select([*keys, "objective", "total", "pursued"]).sort([*keys, "objective"])
