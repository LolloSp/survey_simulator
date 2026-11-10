"""Schema Pydantic del file di configurazione YAML.

Rispecchia la sezione "Configurazione parametrica" di docs/SPEC.md. Qui stanno
i vincoli esprimibili campo per campo o dentro una singola sezione; i controlli
incrociati fra sezioni e quelli che dipendono dal registro delle sorgenti dati
stanno in `rules.py`.
"""

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Base comune: chiavi sconosciute rifiutate, così un refuso è un errore."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Allocation(StrEnum):
    QUOTA = "quota"
    PROPORTIONAL = "proportional"


class Design(StrEnum):
    WITHIN_SUBJECT = "within_subject"
    BETWEEN_SUBJECT = "between_subject"


class Mode(StrEnum):
    CAWI = "cawi"
    CATI = "cati"
    CAPI = "capi"


class OutputFormat(StrEnum):
    PARQUET = "parquet"
    CSV = "csv"
    SAV = "sav"


# Valore di un filtro: "all", un intervallo [min, max] oppure una lista di categorie.
FilterValue = Literal["all"] | tuple[int, int] | list[str]

Share = Annotated[float, Field(gt=0, le=1)]


def _check_unique(values: list[str], label: str) -> list[str]:
    duplicati = sorted({v for v in values if values.count(v) > 1})
    if duplicati:
        raise ValueError(f"{label} contiene duplicati: {', '.join(duplicati)}")
    return values


class ProjectConfig(StrictModel):
    name: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    seed: int = Field(ge=0)


LISTA_CLIENTI = "lista_clienti"


class ContactsSpec(StrictModel):
    """Anagrafica del committente come campione (sorgente `lista_clienti`, M13)."""

    path: Path
    unit: Literal["individui", "imprese"] | None = None  # None: riga per riga
    sheet: str | None = None
    mapping: dict[str, str] = Field(default_factory=dict)  # campo canonico -> intestazione
    keep: dict[str, list[str]] = Field(default_factory=dict)  # colonna -> valori ammessi


class SegmentConfig(StrictModel):
    share: Share | None = None
    size: int | None = Field(default=None, gt=0)
    source: str = Field(min_length=1)
    contacts: ContactsSpec | None = None
    filters: dict[str, FilterValue] = Field(default_factory=dict)
    quotas: list[str] = Field(default_factory=list)
    oversample: dict[str, dict[str, Share]] = Field(default_factory=dict)
    respondent_role: list[str] | None = Field(default=None, min_length=1)

    @field_validator("quotas")
    @classmethod
    def _quotas_uniche(cls, v: list[str]) -> list[str]:
        return _check_unique(v, "quotas")

    @model_validator(mode="after")
    def _contacts_coerenti(self) -> "SegmentConfig":
        if self.source == LISTA_CLIENTI and self.contacts is None:
            raise ValueError("source lista_clienti richiede il blocco contacts (path del file)")
        if self.source != LISTA_CLIENTI and self.contacts is not None:
            raise ValueError("contacts è ammesso solo con source lista_clienti")
        if self.source != LISTA_CLIENTI and not self.quotas:
            raise ValueError("quotas: almeno una variabile di quota per le sorgenti ISTAT")
        return self

    @field_validator("respondent_role")
    @classmethod
    def _ruoli_unici(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _check_unique(v, "respondent_role")

    @field_validator("oversample")
    @classmethod
    def _oversample_somma_a_uno(cls, v: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        for variabile, proporzioni in v.items():
            totale = sum(proporzioni.values())
            if abs(totale - 1.0) > 1e-6:
                raise ValueError(
                    f"oversample.{variabile}: le proporzioni sommano a {totale:.4f}, non a 1"
                )
        return v


class SampleConfig(StrictModel):
    total: int | None = Field(default=None, gt=0)  # null solo con lista_clienti
    allocation: Allocation = Allocation.QUOTA
    segments: dict[str, SegmentConfig] = Field(min_length=1)


class QuestionnaireConfig(StrictModel):
    path: Path


class ModesConfig(StrictModel):
    design: Design = Design.WITHIN_SUBJECT
    enabled: list[Mode] = Field(min_length=1)
    allocation: dict[Mode, Share] | None = None

    @field_validator("enabled")
    @classmethod
    def _modalita_uniche(cls, v: list[Mode]) -> list[Mode]:
        _check_unique([m.value for m in v], "modes.enabled")
        return v

    @model_validator(mode="after")
    def _allocazione_coerente(self) -> "ModesConfig":
        if self.design is Design.BETWEEN_SUBJECT:
            if self.allocation is None:
                raise ValueError(
                    "modes.allocation è obbligatoria con design between_subject "
                    "(una proporzione per ogni modalità abilitata)"
                )
            abilitate = set(self.enabled)
            assegnate = set(self.allocation)
            if abilitate != assegnate:
                mancanti = sorted(m.value for m in abilitate - assegnate)
                extra = sorted(m.value for m in assegnate - abilitate)
                dettagli = []
                if mancanti:
                    dettagli.append(f"mancano {', '.join(mancanti)}")
                if extra:
                    dettagli.append(f"non abilitate {', '.join(extra)}")
                raise ValueError(
                    "modes.allocation deve coprire esattamente le modalità abilitate: "
                    + "; ".join(dettagli)
                )
            totale = sum(self.allocation.values())
            if abs(totale - 1.0) > 1e-6:
                raise ValueError(f"modes.allocation somma a {totale:.4f}, non a 1")
        return self


# Provider LLM implementati: "anthropic" (M6), "openai" (M12), "session" (M14, la sessione
# di Claude Code risponde su file) e "fake" per i test.
KNOWN_PROVIDERS: tuple[str, ...] = ("anthropic", "fake", "openai", "session")


class ModelSpec(StrictModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)

    @field_validator("provider")
    @classmethod
    def _provider_noto(cls, v: str) -> str:
        if v not in KNOWN_PROVIDERS:
            raise ValueError(f"provider '{v}' sconosciuto; noti: {', '.join(KNOWN_PROVIDERS)}")
        return v


class NonverbalConfig(StrictModel):
    enabled: bool = True
    vocabulary: str = Field(default="default", min_length=1)


class EngineConfig(StrictModel):
    models: list[ModelSpec] = Field(min_length=1)
    # Temperatura: solo per provider che la supportano; i modelli Claude attuali
    # la rifiutano e l'adapter la ignora con un avviso.
    temperature: float | None = Field(default=None, ge=0, le=2)
    effort: Literal["low", "medium", "high"] = "low"  # profondità di ragionamento
    max_tokens: int = Field(default=1024, ge=16)  # per singola risposta
    concurrency: int = Field(default=4, ge=1)  # chiamate LLM in parallelo
    timeout_s: float = Field(default=120.0, gt=0)  # per singola chiamata
    cache_dir: Path | None = None  # default: <output.dir>/.cache
    eur_per_usd: float = Field(default=0.92, gt=0)  # cambio per il budget in euro
    replicates: int = Field(default=3, ge=1)
    randomize_option_order: bool = True
    nonverbal: NonverbalConfig = NonverbalConfig()

    @field_validator("models")
    @classmethod
    def _modelli_unici(cls, v: list[ModelSpec]) -> list[ModelSpec]:
        _check_unique([f"{m.provider}/{m.model}" for m in v], "engine.models")
        return v


class RunConfig(StrictModel):
    pilot: bool = False
    pilot_size: int = Field(default=12, ge=1)
    frozen: bool = False
    budget_max_eur: float = Field(gt=0)


class OutputConfig(StrictModel):
    formats: list[OutputFormat] = Field(
        default=[OutputFormat.PARQUET, OutputFormat.CSV, OutputFormat.SAV], min_length=1
    )
    dir: Path = Path("runs")

    @field_validator("formats")
    @classmethod
    def _formati_unici(cls, v: list[OutputFormat]) -> list[OutputFormat]:
        _check_unique([f.value for f in v], "output.formats")
        return v


class PersonasConfig(StrictModel):
    """Opzioni per la costruzione delle persone (M4)."""

    priors_path: Path | None = None  # sostituisce i priori di default (YAML)
    include_names: bool = True  # nome di battesimo nella narrativa


class SurveySimulatorConfig(StrictModel):
    """Radice della configurazione di progetto."""

    project: ProjectConfig
    sample: SampleConfig
    questionnaire: QuestionnaireConfig
    personas: PersonasConfig = PersonasConfig()
    modes: ModesConfig
    engine: EngineConfig
    run: RunConfig
    output: OutputConfig = OutputConfig()
