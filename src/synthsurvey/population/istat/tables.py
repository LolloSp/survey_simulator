"""Registro delle tavole ISTAT: dataflow, chiave, periodo e normalizzazione.

Cambiare anno di riferimento significa cambiare qui il periodo e rigenerare
le tavole con `synthsurvey data fetch`. I dataflow e le chiavi sono stati
verificati con scripts/istat_explore.py il 5 novembre 2026.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import polars as pl

from synthsurvey.population.istat import codelists as cl
from synthsurvey.population.istat import normalize as nz


class Normalizer(Protocol):
    def __call__(
        self, texts: list[str], period: str, *, required_regions: Iterable[str] = ...
    ) -> pl.DataFrame: ...


REGIONI = "+".join(cl.REGION_CODES)


@dataclass(frozen=True)
class SdmxRequest:
    dataflow: str
    key: str
    start: str
    end: str


@dataclass(frozen=True)
class TableSpec:
    name: str
    description: str
    source_name: str  # nome ISTAT della fonte
    period: str  # periodo di riferimento usato nel filtro
    requests: tuple[SdmxRequest, ...]
    normalize: Normalizer
    columns: tuple[str, ...]

    @property
    def filename(self) -> str:
        return f"{self.name}.csv"


_LFS_AGES = "+".join(cl.AGE_CLASS_LFS)
_LFS_EDU = "+".join(cl.EDUCATION_LFS) + "+" + cl.EDUCATION_LFS_TOTAL
_CENSUS_EDU = "+".join(cl.EDUCATION_CENSUS) + "+" + cl.EDUCATION_CENSUS_TOTAL
_CENSUS_EMP = "+".join(cl.EMPLOYMENT_CENSUS) + "+" + cl.EMPLOYMENT_CENSUS_TOTAL

POPULATION = TableSpec(
    name="population_region_sex_age",
    description="Popolazione residente al 1° gennaio per regione, sesso ed età singola (0-100+)",
    source_name="ISTAT, Popolazione residente al 1° gennaio (dataflow 22_289)",
    period="2025",
    requests=(
        SdmxRequest(
            dataflow="22_289_DF_DCIS_POPRES1_1",
            key=f"A.{REGIONI}.JAN.1+2..99",
            start="2025",
            end="2025",
        ),
    ),
    normalize=nz.population_region_sex_age,
    columns=(*nz.REGION_COLUMNS, "sex", "age", "count"),
)

EDUCATION = TableSpec(
    name="education_region_sex_ageclass",
    description="Popolazione di 9 anni e più per regione, sesso, classe d'età e titolo di studio",
    source_name=(
        "ISTAT, Censimento permanente della popolazione (dataflow DF_DCSS_ISTR_LAV_PEN_2_TV_1)"
    ),
    period="2024",
    requests=(
        SdmxRequest(
            dataflow="DF_DCSS_ISTR_LAV_PEN_2_TV_1",
            key=(
                f"A.{REGIONI}.RESPOP_AV.M+F.{'+'.join(cl.AGE_CLASS_CENSUS_EDU)}"
                f".TOTAL.{_CENSUS_EDU}.99.ALL.ALL"
            ),
            start="2024",
            end="2024",
        ),
    ),
    normalize=nz.education_region_sex_ageclass,
    columns=(*nz.REGION_COLUMNS, "sex", "age_class", "education", "count"),
)

EMPLOYMENT = TableSpec(
    name="employment_region_sex_ageclass",
    description=(
        "Popolazione di 15 anni e più per regione, sesso, classe d'età e condizione professionale"
    ),
    source_name=(
        "ISTAT, Censimento permanente della popolazione (dataflow DF_DCSS_ISTR_LAV_PEN_2_TV_3)"
    ),
    period="2024",
    requests=(
        SdmxRequest(
            dataflow="DF_DCSS_ISTR_LAV_PEN_2_TV_3",
            key=(
                f"A.{REGIONI}.RESPOP_AV.M+F.{'+'.join(cl.AGE_CLASS_CENSUS_EMP)}"
                f".TOTAL.ALL.{_CENSUS_EMP}.ALL.ALL"
            ),
            start="2024",
            end="2024",
        ),
    ),
    normalize=nz.employment_region_sex_ageclass,
    columns=(*nz.REGION_COLUMNS, "sex", "age_class", "employment", "count"),
)

EDUCATION_NATIONAL = TableSpec(
    name="education_sex_ageclass_national",
    description="Popolazione di 15 anni e più per sesso, classe d'età e titolo di studio (Italia)",
    source_name="ISTAT, Rilevazione sulle forze di lavoro (dataflow 150_908 e 152_928)",
    period="2024",
    requests=(
        SdmxRequest(
            dataflow="150_908_DF_DCCV_FORZLV1_2",
            key=f"A.IT.FOR.1+2.{_LFS_AGES}.{_LFS_EDU}.TOTAL",
            start="2024",
            end="2024",
        ),
        SdmxRequest(
            dataflow="152_928_DF_DCCV_INATTIV1_2",
            key=f"A.IT.INAC.1+2.{_LFS_AGES}.{_LFS_EDU}.TOTAL.IN.ALL.99",
            start="2024",
            end="2024",
        ),
    ),
    normalize=nz.education_sex_ageclass_national,
    columns=("sex", "age_class", "education", "count"),
)

EMPLOYED_NATIONAL = TableSpec(
    name="employed_sex_ageclass_education_national",
    description="Occupati di 15 anni e più per sesso, classe d'età e titolo di studio (Italia)",
    source_name="ISTAT, Rilevazione sulle forze di lavoro, occupati (dataflow 150_938)",
    period="2024",
    requests=(
        SdmxRequest(
            dataflow="150_938_DF_DCCV_OCCUPATIT1_2",
            key=f"A.IT.1+2.{_LFS_AGES}.{_LFS_EDU}.TOTAL.0010.0010.9.99.99.99.9.9",
            start="2024",
            end="2024",
        ),
    ),
    normalize=nz.employed_sex_ageclass_education_national,
    columns=("sex", "age_class", "education", "count"),
)

FIRMS = TableSpec(
    name="firms_region_sector_size",
    description="Imprese attive per regione, settore (ATECO 2007 accorpato) e classe di addetti",
    source_name="ISTAT, Registro statistico delle imprese attive ASIA (dataflow 183_277)",
    period="2024",
    requests=(
        SdmxRequest(
            dataflow="183_277_DF_DICA_ASIAUE1P_5",
            key=f"A.{REGIONI}.AENTN..{'+'.join(cl.SIZE_CLASS_ASIA)}.TOT.9.9",
            start="2024",
            end="2024",
        ),
    ),
    normalize=nz.firms_region_sector_size,
    columns=(*nz.REGION_COLUMNS, "sector", "size_class", "count"),
)

TABLES: dict[str, TableSpec] = {
    t.name: t
    for t in (POPULATION, EDUCATION, EMPLOYMENT, EDUCATION_NATIONAL, EMPLOYED_NATIONAL, FIRMS)
}

# Tavole richieste da ciascuna sorgente del registro di configurazione.
TABLES_BY_SOURCE: dict[str, tuple[str, ...]] = {
    "istat_individui": (
        POPULATION.name,
        EDUCATION.name,
        EMPLOYMENT.name,
        EDUCATION_NATIONAL.name,
        EMPLOYED_NATIONAL.name,
    ),
    "istat_imprese": (FIRMS.name,),
}


def tables_for_sources(sources: list[str] | tuple[str, ...]) -> list[TableSpec]:
    """Tavole da estrarre per un insieme di sorgenti, senza duplicati e in ordine stabile."""
    nomi: list[str] = []
    for s in sources:
        for n in TABLES_BY_SOURCE.get(s, ()):
            if n not in nomi:
                nomi.append(n)
    return [TABLES[n] for n in nomi]
