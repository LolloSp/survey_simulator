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
from synthsurvey.population.istat import codelists_persone as cp
from synthsurvey.population.istat import normalize as nz
from synthsurvey.population.istat import normalize_persone as npz


class Normalizer(Protocol):
    def __call__(
        self, texts: list[str], period: str, *, required_regions: Iterable[str] = ...
    ) -> pl.DataFrame: ...


REGIONI = "+".join(cl.REGION_CODES)
# EU-SILC: Trentino-Alto Adige solo come province autonome (ITD1, ITD2).
REGIONI_SILC = "+".join(c for c in cl.REGION_CODES if c != "ITDA") + "+ITD1+ITD2"


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

# --------------------------------------------------------------------------- #
# Tavole per le persone (M4): atteggiamenti, reddito, imprese
# --------------------------------------------------------------------------- #

_AVQ_EDU = "3+4+7+11"
_AVQ_AGES_14 = "Y14-24+Y25-44+Y45-64+Y_GE65"
_AVQ_AGES_6 = "Y6-24+Y25-44+Y45-64+Y_GE65"
_PERSON_COLUMNS = ("sex", "age_class", "education", "category", "count")
_AVQ_SOURCE = "ISTAT, Aspetti della vita quotidiana (dataflow 83_63)"
_SECTIONS = "+".join(cp.SECTOR_BY_SECTION)


def _avq_request(flow: int, codes: Iterable[str], ages: str) -> SdmxRequest:
    return SdmxRequest(
        dataflow=f"83_63_DF_DCCV_AVQ_PERSONE_{flow}",
        key=f"A.IT.{'+'.join(codes)}.THV.1+2.{ages}.{_AVQ_EDU}.99",
        start="2024",
        end="2024",
    )


_INTERNET_REQUEST = _avq_request(236, cp.INTERNET_AVQ, _AVQ_AGES_6)

TRUST = TableSpec(
    name="trust_sex_ageclass_education",
    description="Fiducia interpersonale per sesso, classe d'età e titolo di studio (Italia)",
    source_name=_AVQ_SOURCE,
    period="2024",
    requests=(_avq_request(124, cp.TRUST_AVQ, _AVQ_AGES_14),),
    normalize=npz.trust_sex_ageclass_education,
    columns=_PERSON_COLUMNS,
)

LIFE_SATISFACTION = TableSpec(
    name="life_satisfaction_sex_ageclass_education",
    description="Soddisfazione per la vita (0-10) per sesso, classe d'età e titolo di studio",
    source_name=_AVQ_SOURCE,
    period="2024",
    requests=(_avq_request(138, cp.LIFE_SATISFACTION_AVQ, _AVQ_AGES_14),),
    normalize=npz.life_satisfaction_sex_ageclass_education,
    columns=_PERSON_COLUMNS,
)

INTERNET = TableSpec(
    name="internet_sex_ageclass_education",
    description="Uso di internet per frequenza, per sesso, classe d'età e titolo di studio",
    source_name=_AVQ_SOURCE,
    period="2024",
    requests=(_INTERNET_REQUEST,),
    normalize=npz.internet_sex_ageclass_education,
    columns=_PERSON_COLUMNS,
)

POLITICAL_INFO = TableSpec(
    name="political_info_sex_ageclass_education",
    description="Frequenza dell'informazione politica per sesso, classe d'età e titolo di studio",
    source_name=_AVQ_SOURCE,
    period="2024",
    requests=(_avq_request(109, cp.POLITICAL_INFO_AVQ, _AVQ_AGES_14),),
    normalize=npz.political_info_sex_ageclass_education,
    columns=_PERSON_COLUMNS,
)

RELIGION = TableSpec(
    name="religion_sex_ageclass_education",
    description="Frequenza di un luogo di culto per sesso, classe d'età e titolo di studio",
    source_name=_AVQ_SOURCE,
    period="2024",
    requests=(_avq_request(134, cp.RELIGION_AVQ, _AVQ_AGES_6), _INTERNET_REQUEST),
    normalize=npz.religion_sex_ageclass_education,
    columns=_PERSON_COLUMNS,
)

ECONOMIC_JUDGEMENT = TableSpec(
    name="economic_judgement_region",
    description="Giudizio delle famiglie sulle risorse economiche per regione",
    source_name="ISTAT, Aspetti della vita quotidiana, famiglie (dataflow 82_87)",
    period="2024",
    requests=(
        SdmxRequest(
            dataflow="82_87_DF_DCCV_AVQ_FAMIGLIE_14",
            key=f"A.{REGIONI}.{'+'.join(cp.ECONOMIC_JUDGEMENT_AVQ)}.THV.TOT",
            start="2024",
            end="2024",
        ),
    ),
    normalize=npz.economic_judgement_region,
    columns=(*nz.REGION_COLUMNS, "category", "count"),
)

INCOME_MAIN_EARNER = TableSpec(
    name="income_quintile_main_earner",
    description=(
        "Famiglie per quintile di reddito equivalente, per titolo di studio e condizione "
        "del principale percettore (Italia)"
    ),
    source_name="ISTAT, Reddito e condizioni di vita EU-SILC (dataflow 32_38)",
    period="2024",
    requests=(
        SdmxRequest(
            dataflow="32_38_DF_DCCV_QUINTOREDD_5",
            key="A.IT.REDD_QUINTO.10.1+2+3+4+5.1.99.99.9.9.9.9..",
            start="2024",
            end="2024",
        ),
    ),
    normalize=npz.income_quintile_main_earner,
    columns=("dimension", "code", "category", "quintile", "share"),
)

INCOME_REGION = TableSpec(
    name="income_quintile_region",
    description="Famiglie per quintile di reddito equivalente, per regione",
    source_name="ISTAT, Reddito e condizioni di vita EU-SILC (dataflow 32_38)",
    period="2024",
    requests=(
        SdmxRequest(
            dataflow="32_38_DF_DCCV_QUINTOREDD_6",
            key=f"A.{REGIONI_SILC}.REDD_QUINTO.10.1+2+3+4+5.1.99.99.9.9.9.9.99.99",
            start="2024",
            end="2024",
        ),
    ),
    normalize=npz.income_quintile_region,
    columns=(*nz.REGION_COLUMNS, "quintile", "share"),
)

FIRM_RELATIONS = TableSpec(
    name="firm_relations_sector_size",
    description=(
        "Imprese con 3+ addetti e imprese con relazioni con altre imprese, per settore e classe"
    ),
    source_name="ISTAT, Censimento permanente delle imprese 2022 (dataflow 742_1106)",
    period="2022",
    requests=(
        SdmxRequest(
            dataflow="742_1106_DF_DCSI_CPI_RELAZIONI_6",
            key=(
                f"A.IT.AENTN3M+AENTN3M_RELAT.{_SECTIONS}.{'+'.join(cp.SIZE_CLASS_CENSUS)}"
                ".ALL.ALL.ALL.ALL.TOT.TOT.TOT.0010.ALL"
            ),
            start="2022",
            end="2022",
        ),
    ),
    normalize=npz.firm_relations_sector_size,
    columns=("sector", "size_class", "total", "with_relations"),
)

FIRM_OBJECTIVES = TableSpec(
    name="firm_objectives_sector_size",
    description=(
        "Imprese con 10+ addetti e imprese che hanno perseguito obiettivi strategici, "
        "per settore e classe"
    ),
    source_name="ISTAT, Censimento permanente delle imprese 2022 (dataflow 742_1102)",
    period="2022",
    requests=(
        SdmxRequest(
            dataflow="742_1102_DF_DCSI_CPI_CONTROLLO_22",
            key=(
                f"A.IT.AENTN10M.{_SECTIONS}.W10_19+W20_49+W50_99+W100_249.ALL.ALL.ALL.TOT"
                f".{'+'.join(cp.FIRM_OBJECTIVES)}+ALL.OBJPURSUED+ALL.ALL"
            ),
            start="2022",
            end="2022",
        ),
    ),
    normalize=npz.firm_objectives_sector_size,
    columns=("sector", "size_class", "objective", "total", "pursued"),
)

PERSON_TABLES: tuple[TableSpec, ...] = (
    TRUST,
    LIFE_SATISFACTION,
    INTERNET,
    POLITICAL_INFO,
    RELIGION,
    ECONOMIC_JUDGEMENT,
    INCOME_MAIN_EARNER,
    INCOME_REGION,
)
FIRM_PERSON_TABLES: tuple[TableSpec, ...] = (FIRM_RELATIONS, FIRM_OBJECTIVES)

TABLES: dict[str, TableSpec] = {
    t.name: t
    for t in (
        POPULATION,
        EDUCATION,
        EMPLOYMENT,
        EDUCATION_NATIONAL,
        EMPLOYED_NATIONAL,
        FIRMS,
        *PERSON_TABLES,
        *FIRM_PERSON_TABLES,
    )
}

# Tavole richieste da ciascuna sorgente del registro di configurazione.
TABLES_BY_SOURCE: dict[str, tuple[str, ...]] = {
    "istat_individui": (
        POPULATION.name,
        EDUCATION.name,
        EMPLOYMENT.name,
        EDUCATION_NATIONAL.name,
        EMPLOYED_NATIONAL.name,
        *(t.name for t in PERSON_TABLES),
    ),
    "istat_imprese": (FIRMS.name, *(t.name for t in FIRM_PERSON_TABLES)),
}


def tables_for_sources(sources: list[str] | tuple[str, ...]) -> list[TableSpec]:
    """Tavole da estrarre per un insieme di sorgenti, senza duplicati e in ordine stabile."""
    nomi: list[str] = []
    for s in sources:
        for n in TABLES_BY_SOURCE.get(s, ()):
            if n not in nomi:
                nomi.append(n)
    return [TABLES[n] for n in nomi]
