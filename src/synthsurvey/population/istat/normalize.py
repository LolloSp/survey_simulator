"""Normalizzazione delle risposte CSV SDMX nelle tavole del progetto.

Ogni funzione riceve il testo CSV grezzo (uno o più) e restituisce un
DataFrame Polars ordinato con colonne fisse. I controlli di coerenza
(somma delle categorie uguale al totale ISTAT) sollevano `NormalizeError`.
"""

import io
from collections.abc import Iterable

import polars as pl

from synthsurvey.population.istat import codelists as cl

REGION_COLUMNS = ["region_code", "region", "macro_area"]
TOLLERANZA_SOMMA = 0.005  # 0,5% di scarto ammesso fra somma delle categorie e totale ISTAT


class NormalizeError(ValueError):
    """Dati grezzi non conformi a quanto atteso dalla tavola."""


def read_sdmx_csv(text: str) -> pl.DataFrame:
    """Legge un CSV SDMX con tutte le colonne come stringhe."""
    if not text.startswith("DATAFLOW"):
        raise NormalizeError("testo non riconosciuto come CSV SDMX (manca l'intestazione)")
    return pl.read_csv(io.StringIO(text), infer_schema=False)


def _obs_value(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(pl.col("OBS_VALUE").cast(pl.Float64).alias("value"))


def _with_region(df: pl.DataFrame, code_col: str = "REF_AREA") -> pl.DataFrame:
    regions = pl.DataFrame(
        {
            "region_code": list(cl.REGIONS),
            "region": [v[0] for v in cl.REGIONS.values()],
            "macro_area": [v[1] for v in cl.REGIONS.values()],
        }
    )
    return df.rename({code_col: "region_code"}).join(regions, on="region_code", how="inner")


def _map(df: pl.DataFrame, col: str, mapping: dict[str, str], new: str) -> pl.DataFrame:
    """Mappa i codici di `col` con `mapping` in `new`, scartando i codici assenti."""
    table = pl.DataFrame({col: list(mapping), new: list(mapping.values())})
    return df.join(table, on=col, how="inner")


def _check_total(
    df_cat: pl.DataFrame,
    df_tot: pl.DataFrame,
    keys: list[str],
    label: str,
) -> None:
    """Confronta la somma delle categorie con il totale ISTAT per ogni combinazione di chiavi."""
    if df_tot.is_empty():
        return
    somma = df_cat.group_by(keys).agg(pl.col("value").sum().alias("somma"))
    confronto = somma.join(df_tot.select([*keys, pl.col("value").alias("totale")]), on=keys)
    scarti = confronto.filter(
        (pl.col("somma") - pl.col("totale")).abs() > pl.col("totale") * TOLLERANZA_SOMMA
    )
    if not scarti.is_empty():
        riga = scarti.row(0, named=True)
        raise NormalizeError(
            f"{label}: la somma delle categorie ({riga['somma']:.0f}) non torna con il totale "
            f"ISTAT ({riga['totale']:.0f}) per {', '.join(f'{k}={riga[k]}' for k in keys)}"
        )


def _require_rows(df: pl.DataFrame, label: str, period: str) -> None:
    if df.is_empty():
        raise NormalizeError(f"{label}: nessuna riga per il periodo {period}")


def _require_regions(df: pl.DataFrame, label: str, required: Iterable[str]) -> None:
    presenti = set(df["region_code"].unique().to_list())
    mancanti = sorted(set(required) - presenti)
    if mancanti:
        raise NormalizeError(f"{label}: regioni mancanti nei dati: {', '.join(mancanti)}")


def _finalize(df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    out = df.select(columns).with_columns(pl.col("count").round(0).cast(pl.Int64))
    return out.sort([c for c in columns if c != "count"])


# --------------------------------------------------------------------------- #
# Tavole
# --------------------------------------------------------------------------- #


def population_region_sex_age(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Popolazione residente al 1° gennaio per regione, sesso ed età singola (tutte le età)."""
    df = _obs_value(read_sdmx_csv(texts[0]))
    df = df.filter(
        (pl.col("DATA_TYPE") == "JAN")
        & (pl.col("MARITAL_STATUS") == "99")
        & (pl.col("TIME_PERIOD") == period)
    )
    _require_rows(df, "popolazione", period)
    df = _with_region(df)
    _require_regions(df, "popolazione", required_regions)
    df = _map(df, "SEX", cl.SEX_NUMERIC, "sex")
    ages = pl.DataFrame(
        {
            "AGE": [c for c in df["AGE"].unique().to_list() if cl.age_from_code(c) is not None],
        }
    ).with_columns(
        pl.col("AGE")
        .map_elements(lambda c: cl.age_from_code(c), return_dtype=pl.Int64)
        .alias("age")
    )
    df = df.join(ages, on="AGE", how="inner").filter(pl.col("age") >= 0)
    if df.is_empty():
        raise NormalizeError("popolazione: nessuna riga per il periodo richiesto")
    df = df.rename({"value": "count"})
    return _finalize(df, [*REGION_COLUMNS, "sex", "age", "count"])


def education_region_sex_ageclass(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Popolazione di 9 anni e più per regione, sesso, classe d'età e titolo di studio."""
    df = _obs_value(read_sdmx_csv(texts[0]))
    df = df.filter(
        (pl.col("INDICATOR") == "RESPOP_AV")
        & (pl.col("CITIZENSHIP") == "TOTAL")
        & (pl.col("CUR_ACT_STAT") == "99")
        & (pl.col("TIME_PERIOD") == period)
    )
    _require_rows(df, "istruzione", period)
    df = _with_region(df)
    _require_regions(df, "istruzione", required_regions)
    df = _map(df, "GENDER", cl.SEX_LETTER, "sex")
    df = _map(df, "AGE_NOCLASS", cl.AGE_CLASS_CENSUS_EDU, "age_class")
    totali = df.filter(pl.col("EDU_ATTAIN") == cl.EDUCATION_CENSUS_TOTAL)
    cat = _map(df, "EDU_ATTAIN", cl.EDUCATION_CENSUS, "education")
    keys = ["region_code", "sex", "age_class"]
    _check_total(cat, totali, keys, "istruzione")
    out = cat.group_by([*REGION_COLUMNS, "sex", "age_class", "education"]).agg(
        pl.col("value").sum().alias("count")
    )
    return _finalize(out, [*REGION_COLUMNS, "sex", "age_class", "education", "count"])


def employment_region_sex_ageclass(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Popolazione di 15 anni e più per regione, sesso, classe d'età e condizione."""
    df = _obs_value(read_sdmx_csv(texts[0]))
    df = df.filter(
        (pl.col("INDICATOR") == "RESPOP_AV")
        & (pl.col("CITIZENSHIP") == "TOTAL")
        & (pl.col("EDU_ATTAIN") == "ALL")
        & (pl.col("TIME_PERIOD") == period)
    )
    _require_rows(df, "condizione professionale", period)
    df = _with_region(df)
    _require_regions(df, "condizione professionale", required_regions)
    df = _map(df, "GENDER", cl.SEX_LETTER, "sex")
    df = _map(df, "AGE_NOCLASS", cl.AGE_CLASS_CENSUS_EMP, "age_class")
    totali = df.filter(pl.col("CUR_ACT_STAT") == cl.EMPLOYMENT_CENSUS_TOTAL)
    cat = _map(df, "CUR_ACT_STAT", cl.EMPLOYMENT_CENSUS, "employment")
    keys = ["region_code", "sex", "age_class"]
    _check_total(cat, totali, keys, "condizione professionale")
    out = cat.group_by([*REGION_COLUMNS, "sex", "age_class", "employment"]).agg(
        pl.col("value").sum().alias("count")
    )
    return _finalize(out, [*REGION_COLUMNS, "sex", "age_class", "employment", "count"])


def education_sex_ageclass_national(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Popolazione di 15 anni e più per sesso, classe d'età fine e titolo di studio (Italia).

    Somma di forze di lavoro e inattivi dalla Rilevazione sulle forze di lavoro;
    i valori ISTAT sono in migliaia e vengono riportati a persone.
    """
    parti = []
    for text, tipo in zip(texts, ("FOR", "INAC"), strict=True):
        df = _obs_value(read_sdmx_csv(text))
        df = df.filter(
            (pl.col("REF_AREA") == "IT")
            & (pl.col("DATA_TYPE") == tipo)
            & (pl.col("CITIZENSHIP") == "TOTAL")
            & (pl.col("TIME_PERIOD") == period)
        )
        df = _map(df, "SEX", cl.SEX_NUMERIC, "sex")
        df = _map(df, "AGE", cl.AGE_CLASS_LFS, "age_class")
        totali = df.filter(pl.col("EDU_LEV_HIGHEST") == cl.EDUCATION_LFS_TOTAL)
        cat = _map(df, "EDU_LEV_HIGHEST", cl.EDUCATION_LFS, "education")
        _check_total(cat, totali, ["sex", "age_class"], f"forze di lavoro ({tipo})")
        parti.append(cat.select(["sex", "age_class", "education", "value"]))
    df = pl.concat(parti)
    if df.is_empty():
        raise NormalizeError("forze di lavoro: nessuna riga per il periodo richiesto")
    out = df.group_by(["sex", "age_class", "education"]).agg(
        (pl.col("value").sum() * 1000).alias("count")
    )
    return _finalize(out, ["sex", "age_class", "education", "count"])


def firms_region_sector_size(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Imprese attive (registro ASIA) per regione, settore e classe di addetti."""
    df = _obs_value(read_sdmx_csv(texts[0]))
    df = df.filter(
        (pl.col("DATA_TYPE") == "AENTN")
        & (pl.col("LEGAL_FORM") == "TOT")
        & (pl.col("Y_ENTER_WITH_EMPLOYEES") == "9")
        & (pl.col("Y_CRAFTMEN") == "9")
        & (pl.col("TIME_PERIOD") == period)
    )
    _require_rows(df, "imprese", period)
    df = _with_region(df)
    _require_regions(df, "imprese", required_regions)
    df = _map(df, "PERS_EMPL_SIZE_CLASS", cl.SIZE_CLASS_ASIA, "size_class")
    df = _map(df, "ECON_ACTIVITY_NACE_2007", cl.SECTOR_BY_DIVISION, "sector")
    if df.is_empty():
        raise NormalizeError("imprese: nessuna riga per il periodo richiesto")
    out = df.group_by([*REGION_COLUMNS, "sector", "size_class"]).agg(
        pl.col("value").sum().alias("count")
    )
    return _finalize(out, [*REGION_COLUMNS, "sector", "size_class", "count"])


def employed_sex_ageclass_education_national(
    texts: list[str], period: str, *, required_regions: Iterable[str] = cl.REGION_CODES
) -> pl.DataFrame:
    """Occupati di 15 anni e più per sesso, classe d'età fine e titolo di studio (Italia).

    Dalla Rilevazione sulle forze di lavoro, valori in migliaia riportati a persone.
    Serve a dare all'IPF l'associazione fra istruzione e condizione professionale.
    """
    df = _obs_value(read_sdmx_csv(texts[0]))
    df = df.filter(
        (pl.col("REF_AREA") == "IT")
        & (pl.col("CITIZENSHIP") == "TOTAL")
        & (pl.col("TIME_PERIOD") == period)
    )
    df = _map(df, "SEX", cl.SEX_NUMERIC, "sex")
    df = _map(df, "AGE", cl.AGE_CLASS_LFS, "age_class")
    totali = df.filter(pl.col("EDU_LEV_HIGHEST") == cl.EDUCATION_LFS_TOTAL)
    cat = _map(df, "EDU_LEV_HIGHEST", cl.EDUCATION_LFS, "education")
    if cat.is_empty():
        raise NormalizeError(f"occupati: nessuna riga per il periodo {period}")
    _check_total(cat, totali, ["sex", "age_class"], "occupati")
    out = cat.group_by(["sex", "age_class", "education"]).agg(
        (pl.col("value").sum() * 1000).alias("count")
    )
    return _finalize(out, ["sex", "age_class", "education", "count"])
