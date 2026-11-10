"""Registro delle sorgenti dati per i segmenti.

Ogni sorgente dichiara l'unità statistica, le variabili di quota ammesse con le
loro categorie, i filtri ammessi e, per le imprese, i ruoli del rispondente.
È il solo punto da estendere per aggiungere un nuovo tipo di segmento (ad esempio
grandi imprese o pubblica amministrazione). Le categorie vengono da
`survey_simulator.population.categories`, condivise con la normalizzazione ISTAT.
"""

from dataclasses import dataclass, field
from typing import Literal

from survey_simulator.population import categories as cat

Unit = Literal["individui", "imprese"]


@dataclass(frozen=True)
class QuotaVariable:
    name: str
    categories: tuple[str, ...]


@dataclass(frozen=True)
class RangeFilter:
    """Filtro su intervallo numerico chiuso, con limiti plausibili."""

    name: str
    min_allowed: int
    max_allowed: int


@dataclass(frozen=True)
class CategoricalFilter:
    """Filtro su lista di categorie, oppure "all"."""

    name: str
    categories: tuple[str, ...]


FilterSpec = RangeFilter | CategoricalFilter


@dataclass(frozen=True)
class DataSource:
    name: str
    unit: Unit
    quota_variables: dict[str, QuotaVariable]
    filters: dict[str, FilterSpec]
    respondent_roles: tuple[str, ...] = ()
    # Per le imprese: intervallo di addetti di ciascuna classe dimensionale.
    size_class_bounds: dict[str, tuple[int, int]] = field(default_factory=dict)


def _vars(*variabili: QuotaVariable) -> dict[str, QuotaVariable]:
    return {v.name: v for v in variabili}


def _filters(*filtri: FilterSpec) -> dict[str, FilterSpec]:
    return {f.name: f for f in filtri}


ISTAT_INDIVIDUI = DataSource(
    name="istat_individui",
    unit="individui",
    quota_variables=_vars(
        QuotaVariable("sex", cat.SEX),
        QuotaVariable("age_band", cat.AGE_BANDS),
        QuotaVariable("macro_area", cat.MACRO_AREAS),
        QuotaVariable("education", cat.EDUCATION),
        QuotaVariable("employment", cat.EMPLOYMENT),
    ),
    filters=_filters(
        RangeFilter("age", 18, 99),
        CategoricalFilter("region", cat.REGIONS),
        CategoricalFilter("macro_area", cat.MACRO_AREAS),
    ),
)

ISTAT_IMPRESE = DataSource(
    name="istat_imprese",
    unit="imprese",
    quota_variables=_vars(
        QuotaVariable("size_class", cat.SIZE_CLASSES_PMI),
        QuotaVariable("sector", cat.SECTORS),
        QuotaVariable("macro_area", cat.MACRO_AREAS),
    ),
    filters=_filters(
        RangeFilter("employees", 1, 249),
        CategoricalFilter("sectors", cat.SECTORS),
        CategoricalFilter("macro_area", cat.MACRO_AREAS),
    ),
    respondent_roles=cat.RESPONDENT_ROLES,
    size_class_bounds=cat.SIZE_CLASS_BOUNDS,
)

# Anagrafica del committente (M13): nessuna variabile di quota né filtro; l'unità
# (individuo o impresa) è decisa record per record, qui vale solo come etichetta.
LISTA_CLIENTI = DataSource(
    name="lista_clienti",
    unit="individui",
    quota_variables={},
    filters={},
    respondent_roles=cat.RESPONDENT_ROLES,
    size_class_bounds=dict(cat.SIZE_CLASS_BOUNDS),
)

SOURCES: dict[str, DataSource] = {
    s.name: s for s in (ISTAT_INDIVIDUI, ISTAT_IMPRESE, LISTA_CLIENTI)
}


class UnknownSourceError(KeyError):
    """Sorgente dati non presente nel registro."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"sorgente '{self.name}' sconosciuta; disponibili: {', '.join(sorted(SOURCES))}"


def get_source(name: str) -> DataSource:
    try:
        return SOURCES[name]
    except KeyError:
        raise UnknownSourceError(name) from None
