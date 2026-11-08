"""Dalle anagrafiche alle unità del campione (sorgente `lista_clienti`, M13).

Ogni record valido diventa un'unità con peso 1. Ciò che il file non dice
viene estratto dalle distribuzioni ISTAT condizionate a ciò che dice:
istruzione e condizione professionale dalla congiunta degli individui
(regione x sesso x gruppo d'età), settore e classe dimensionale dalle
imprese attive per regione. I flag `*_known` dicono alle persone (M4) quali
attributi vengono dal file e quali da ISTAT.
"""

from dataclasses import dataclass

import numpy as np
import polars as pl

from synthsurvey.config.schema import SegmentConfig
from synthsurvey.population import categories as cat
from synthsurvey.population.contacts import ContactsResult
from synthsurvey.population.individui import (
    AGE_GROUP_LABELS,
    EDUCATION,
    EMPLOYMENT,
    REGION_CODES,
    SEX,
    IndividuiPopulation,
    age_group_of,
)
from synthsurvey.population.sampling import DrawResult
from synthsurvey.population.tables import IstatTables
from synthsurvey.population.weights import WeightResult

SOURCE_NAME = "lista_clienti"
UNIT_SCHEMA: dict[str, type[pl.DataType]] = {
    "unit_id": pl.String,
    "segment": pl.String,
    "source": pl.String,
    "unit_kind": pl.String,
    "region_code": pl.String,
    "region": pl.String,
    "macro_area": pl.String,
    "province": pl.String,
    "sex": pl.String,
    "age": pl.Int64,
    "age_band": pl.String,
    "education": pl.String,
    "employment": pl.String,
    "sector": pl.String,
    "size_class": pl.String,
    "respondent_role_known": pl.String,
    "sex_known": pl.Boolean,
    "age_known": pl.Boolean,
    "sector_known": pl.Boolean,
    "size_known": pl.Boolean,
    "weight": pl.Float64,
    "weight_pop": pl.Float64,
}


@dataclass(frozen=True)
class ContactsUnits:
    units: pl.DataFrame
    private_map: pl.DataFrame  # unit_id, record_id, row: resta nella cartella privata del run
    warnings: list[str]


def draw_education_employment(
    pop: IndividuiPopulation, region_code: str, sex: str, age: int, rng: np.random.Generator
) -> tuple[str, str]:
    """Istruzione e condizione dalla congiunta IPF condizionata a regione, sesso, età."""
    r = REGION_CODES.index(region_code)
    s = SEX.index(sex)
    a = AGE_GROUP_LABELS.index(age_group_of(min(age, 100)))
    cella = pop.table[r, s, a, :, :].astype(np.float64)
    p = cella.ravel()
    if p.sum() <= 0:
        p = pop.table[:, s, a, :, :].sum(axis=0).astype(np.float64).ravel()
    if p.sum() <= 0:
        p = np.ones_like(p)
    k = int(rng.choice(len(p), p=p / p.sum()))
    e, m = divmod(k, len(EMPLOYMENT))
    return EDUCATION[e], EMPLOYMENT[m]


def draw_firm_cell(
    firms: pl.DataFrame,
    region_code: str,
    sector: str | None,
    rng: np.random.Generator,
) -> tuple[str, str]:
    """Settore (se mancante) e classe dimensionale dalle imprese attive della regione."""
    sub = firms.filter(pl.col("region_code") == region_code)
    if sector is not None:
        sub = sub.filter(pl.col("sector") == sector)
    sub = sub.filter(pl.col("size_class").is_in(list(cat.SIZE_CLASSES_PMI)))
    if sub.height == 0:
        sub = firms.filter(pl.col("size_class").is_in(list(cat.SIZE_CLASSES_PMI)))
        if sector is not None:
            sub = sub.filter(pl.col("sector") == sector)
    if sub.height == 0:
        return sector or cat.SECTORS[0], "micro"
    pesi = sub["count"].cast(pl.Float64).to_numpy()
    k = int(rng.choice(sub.height, p=pesi / pesi.sum()))
    riga = sub.row(k, named=True)
    return str(riga["sector"]), str(riga["size_class"])


def build_contacts_units(
    name: str,
    seg: SegmentConfig,
    contacts: ContactsResult,
    individui: IndividuiPopulation | None,
    tables: IstatTables,
    rng: np.random.Generator,
) -> ContactsUnits:
    recs = contacts.records.sort("row")
    avvisi: list[str] = []
    if seg.size is not None and seg.size < recs.height:
        scelti = np.sort(rng.choice(recs.height, size=seg.size, replace=False))
        recs = recs[scelti.tolist()]
        avvisi.append(f"{name}: sottocampione casuale di {seg.size} record su {contacts.n}")
    righe = []
    mappa = []
    firms = tables.firms
    for i, r in enumerate(recs.to_dicts()):
        unit_id = f"{name}_{i + 1:05d}"
        kind = r["unit"]
        education = employment = None
        sector, size_class = r["sector"], r["size_class"]
        if kind == "individui":
            if individui is None:
                raise AssertionError("popolazione individui non costruita")
            education, employment = draw_education_employment(
                individui, r["region_code"], r["sex"], int(r["age"]), rng
            )
        else:
            if sector is None or size_class is None:
                sector_d, size_d = draw_firm_cell(firms, r["region_code"], sector, rng)
                sector = sector or sector_d
                size_class = size_class or size_d
        righe.append(
            {
                "unit_id": unit_id,
                "segment": name,
                "source": SOURCE_NAME,
                "unit_kind": kind,
                "region_code": r["region_code"],
                "region": r["region"],
                "macro_area": r["macro_area"],
                "province": r["province"],
                "sex": r["sex"],
                "age": r["age"],
                "age_band": r["age_band"],
                "education": education,
                "employment": employment,
                "sector": sector,
                "size_class": size_class,
                "respondent_role_known": r["role"],
                "sex_known": bool(r["sex_known"]),
                "age_known": bool(r["age_known"]),
                "sector_known": bool(r["sector_known"]),
                "size_known": bool(r["size_known"]),
                "weight": 1.0,
                "weight_pop": 1.0,
            }
        )
        mappa.append({"unit_id": unit_id, "record_id": r["record_id"], "row": r["row"]})
    units = pl.DataFrame(righe, schema=UNIT_SCHEMA)
    private = pl.DataFrame(
        mappa, schema={"unit_id": pl.String, "record_id": pl.String, "row": pl.Int64}
    )
    return ContactsUnits(units=units, private_map=private, warnings=avvisi)


def empty_draw(n: int) -> DrawResult:
    return DrawResult(counts=np.ones(n, dtype=np.int64), achieved={}, max_deviation=0, swaps=0)


def unit_weights(n: int) -> WeightResult:
    uno = np.ones(n, dtype=np.float64)
    return WeightResult(
        weight=uno, weight_pop=uno.copy(), iterations=0, max_rel_error=0.0, warnings=[]
    )
