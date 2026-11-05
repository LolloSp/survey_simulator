"""Registro delle sorgenti dati per i segmenti.

Ogni sorgente dichiara l'unità statistica, le variabili di quota ammesse con le
loro categorie, i filtri ammessi e, per le imprese, i ruoli del rispondente.
È il solo punto da estendere per aggiungere un nuovo tipo di segmento (ad esempio
grandi imprese o pubblica amministrazione). In M2 le categorie vengono allineate
alle tabelle ISTAT normalizzate.

Le categorie elencate qui sono quelle usate per la validazione strutturale e per
la stima delle celle piccole; non contengono alcuna frequenza.
"""

from dataclasses import dataclass, field
from typing import Literal

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


REGIONI: tuple[str, ...] = (
    "piemonte",
    "valle_daosta",
    "lombardia",
    "trentino_alto_adige",
    "veneto",
    "friuli_venezia_giulia",
    "liguria",
    "emilia_romagna",
    "toscana",
    "umbria",
    "marche",
    "lazio",
    "abruzzo",
    "molise",
    "campania",
    "puglia",
    "basilicata",
    "calabria",
    "sicilia",
    "sardegna",
)

MACRO_AREE: tuple[str, ...] = ("nord_ovest", "nord_est", "centro", "sud", "isole")

SETTORI: tuple[str, ...] = (
    "industria",
    "costruzioni",
    "commercio",
    "trasporti_turismo",
    "servizi_imprese",
    "altri_servizi",
)

SIZE_CLASS_BOUNDS: dict[str, tuple[int, int]] = {
    "micro": (1, 9),
    "piccola": (10, 49),
    "media": (50, 249),
}

ISTAT_INDIVIDUI = DataSource(
    name="istat_individui",
    unit="individui",
    quota_variables=_vars(
        QuotaVariable("sex", ("m", "f")),
        QuotaVariable("age_band", ("18_24", "25_34", "35_44", "45_54", "55_64", "65_plus")),
        QuotaVariable("macro_area", MACRO_AREE),
        QuotaVariable("education", ("fino_media", "diploma", "laurea_o_oltre")),
        QuotaVariable("employment", ("occupato", "in_cerca", "pensionato", "altro_inattivo")),
        QuotaVariable("income_band", ("basso", "medio_basso", "medio_alto", "alto")),
    ),
    filters=_filters(
        RangeFilter("age", 18, 99),
        CategoricalFilter("region", REGIONI),
        CategoricalFilter("macro_area", MACRO_AREE),
    ),
)

ISTAT_IMPRESE = DataSource(
    name="istat_imprese",
    unit="imprese",
    quota_variables=_vars(
        QuotaVariable("size_class", tuple(SIZE_CLASS_BOUNDS)),
        QuotaVariable("sector", SETTORI),
        QuotaVariable("macro_area", MACRO_AREE),
    ),
    filters=_filters(
        RangeFilter("employees", 1, 249),
        CategoricalFilter("sectors", SETTORI),
        CategoricalFilter("macro_area", MACRO_AREE),
    ),
    respondent_roles=("titolare", "responsabile_acquisti", "amministratore", "altro"),
    size_class_bounds=SIZE_CLASS_BOUNDS,
)

SOURCES: dict[str, DataSource] = {s.name: s for s in (ISTAT_INDIVIDUI, ISTAT_IMPRESE)}


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
