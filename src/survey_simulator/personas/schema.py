"""Schema Pydantic della persona e dei priori YAML."""

from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from survey_simulator.population import categories as cat


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(StrEnum):
    """Da dove viene un attributo: il report deve distinguere dati e ipotesi."""

    CAMPIONE = "campione"  # dal campione di M3 (ISTAT via IPF e quote)
    ANAGRAFICA = "anagrafica"  # dal file di anagrafiche del committente (M13)
    ISTAT = "istat"  # estratto da una distribuzione ISTAT condizionata al profilo
    ISTAT_PROXY = "istat_proxy"  # distribuzione ISTAT di un gruppo vicino (es. microimprese)
    IPOTESI = "ipotesi"  # priori dichiarati in YAML, nessuna fonte statistica


Level3 = Literal["basso", "medio", "alto"]


class Attitudes(StrictModel):
    trust: str  # si_fida | diffida
    life_satisfaction: int = Field(ge=0, le=10)
    internet: str  # quotidiano | occasionale | mai
    political_info: str  # quotidiana | settimanale | saltuaria | mai
    religion: str  # settimanale | saltuaria | mai
    # Tratti senza fonte ISTAT (ipotesi), in [0, 1].
    sensibilita_prezzo: float = Field(ge=0, le=1)
    fedelta_marca: float = Field(ge=0, le=1)
    propensione_rischio: float = Field(ge=0, le=1)
    apertura_novita: float = Field(ge=0, le=1)


class ResponseStyle(StrictModel):
    acquiescenza: float = Field(ge=0, le=1)
    desiderabilita_sociale: float = Field(ge=0, le=1)
    non_so: float = Field(ge=0, le=1)
    tempo_disponibile: float = Field(ge=0, le=1)
    loquacita: float = Field(ge=0, le=1)

    def labels(self) -> dict[str, Level3]:
        return {k: level3(v) for k, v in self.model_dump().items()}


def level3(x: float) -> Level3:
    if x < 0.35:
        return "basso"
    if x < 0.65:
        return "medio"
    return "alto"


class Firm(StrictModel):
    sector: str
    size_class: str
    employees: int = Field(ge=1)
    respondent_role: str
    with_relations: bool
    objectives: list[str] = Field(default_factory=list)


class Persona(StrictModel):
    persona_id: str
    unit_id: str
    segment: str
    source: str
    # Demografia (dal campione, più reddito e giudizio economico assegnati qui).
    region: str
    macro_area: str
    sex: str
    age: int = Field(ge=18)
    age_band: str
    education: str | None = None
    employment: str | None = None
    income_quintile: int = Field(ge=1, le=5)
    economic_judgement: str  # ottime | adeguate | scarse | insufficienti
    firm: Firm | None = None
    attitudes: Attitudes
    response_style: ResponseStyle
    name: str | None = None
    narrative: str = ""
    provenance: dict[str, Provenance]
    source_versions: dict[str, str] = Field(default_factory=dict)
    weight: float = Field(gt=0)
    weight_pop: float = Field(gt=0)

    @model_validator(mode="after")
    def _coerenza_minima(self) -> "Persona":
        if self.source == "istat_imprese" and self.firm is None:
            raise ValueError("persona d'impresa senza attributi dell'impresa")
        if self.source == "istat_individui" and (self.education is None or self.employment is None):
            raise ValueError("persona individuo senza istruzione o condizione")
        return self


# --------------------------------------------------------------------------- #
# Priori YAML
# --------------------------------------------------------------------------- #


class BetaPrior(StrictModel):
    description: str = ""
    base: float = Field(gt=0, lt=1)
    concentration: float = Field(gt=0)
    modifiers: dict[str, dict[str, float]] = Field(default_factory=dict)


class FirmRespondentPrior(StrictModel):
    female_share: dict[str, float]
    age_range: dict[str, tuple[int, int]]


class IncomePrior(StrictModel):
    employed_split: dict[str, float]
    education_split: dict[str, float]


class CoherencePrior(StrictModel):
    max_attempts: int = Field(default=10, ge=1)


class Priors(StrictModel):
    version: int
    traits: dict[str, BetaPrior]
    response_style: dict[str, BetaPrior]
    firm_response_style: dict[str, dict[str, dict[str, float]]] = Field(default_factory=dict)
    respondent_roles: dict[str, dict[str, float]]
    firm_respondent: FirmRespondentPrior
    income: IncomePrior
    employees: dict[str, tuple[int, int]]
    coherence: CoherencePrior = CoherencePrior()

    @model_validator(mode="after")
    def _controlli(self) -> "Priors":
        attesi_tratti = {
            "sensibilita_prezzo",
            "fedelta_marca",
            "propensione_rischio",
            "apertura_novita",
        }
        if set(self.traits) != attesi_tratti:
            raise ValueError(f"traits deve contenere esattamente {sorted(attesi_tratti)}")
        attesi_stile = {
            "acquiescenza",
            "desiderabilita_sociale",
            "non_so",
            "tempo_disponibile",
            "loquacita",
        }
        if set(self.response_style) != attesi_stile:
            raise ValueError(f"response_style deve contenere esattamente {sorted(attesi_stile)}")
        for classe in cat.SIZE_CLASSES_PMI:
            if classe not in self.respondent_roles:
                raise ValueError(f"respondent_roles manca della classe {classe}")
            quote = self.respondent_roles[classe]
            if set(quote) - set(cat.RESPONDENT_ROLES):
                raise ValueError(f"respondent_roles.{classe}: ruoli sconosciuti")
            if abs(sum(quote.values()) - 1) > 1e-6:
                raise ValueError(f"respondent_roles.{classe}: le quote non sommano a 1")
            if classe not in self.employees:
                raise ValueError(f"employees manca della classe {classe}")
        for nome, extra in self.firm_response_style.items():
            if nome not in self.response_style:
                raise ValueError(f"firm_response_style.{nome}: dimensione sconosciuta")
            if set(extra) - {"respondent_role", "size_class"}:
                raise ValueError(
                    f"firm_response_style.{nome}: chiavi ammesse respondent_role, size_class"
                )
        if abs(sum(self.income.employed_split.values()) - 1) > 1e-6:
            raise ValueError("income.employed_split non somma a 1")
        if abs(sum(self.income.education_split.values()) - 1) > 1e-6:
            raise ValueError("income.education_split non somma a 1")
        return self


class Names(StrictModel):
    version: int
    decades: list[int]
    f: dict[int, list[str]]
    m: dict[int, list[str]]

    @model_validator(mode="after")
    def _decenni(self) -> "Names":
        for sesso in ("f", "m"):
            liste = getattr(self, sesso)
            if set(liste) != set(self.decades):
                raise ValueError(f"nomi {sesso}: decenni diversi da {self.decades}")
            if any(not v for v in liste.values()):
                raise ValueError(f"nomi {sesso}: lista vuota")
        return self


PRIORS_DIR = Path(__file__).parent / "priors"


def load_priors(path: Path | None = None) -> Priors:
    """Carica i priori dal file indicato o da quelli di default del pacchetto."""
    file = path if path is not None else PRIORS_DIR / "default.yaml"
    raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    return Priors.model_validate(raw)


def load_names() -> Names:
    raw = yaml.safe_load((PRIORS_DIR / "names_it.yaml").read_text(encoding="utf-8"))
    return Names.model_validate(raw)
