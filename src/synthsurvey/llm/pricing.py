"""Costi delle chiamate LLM dalla tabella prezzi versionata."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from synthsurvey.llm.client import Usage

PRICES_PATH = Path(__file__).parent / "prices.yaml"
MILLION = 1_000_000


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_write: float = Field(ge=0)
    cache_read: float = Field(ge=0)


class PriceTable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    updated: str
    source: str
    currency: str = "USD"
    models: dict[str, ModelPrice]


class UnknownModelError(KeyError):
    def __init__(self, model: str, known: list[str]) -> None:
        super().__init__(model)
        self.model = model
        self.known = known

    def __str__(self) -> str:
        return f"modello '{self.model}' assente dalla tabella prezzi; noti: {', '.join(self.known)}"


def load_prices(path: Path | None = None) -> PriceTable:
    raw = yaml.safe_load((path or PRICES_PATH).read_text(encoding="utf-8"))
    return PriceTable.model_validate(raw)


@dataclass(frozen=True)
class Pricing:
    table: PriceTable
    eur_per_usd: float = 1.0

    def price(self, model: str) -> ModelPrice:
        try:
            return self.table.models[model]
        except KeyError:
            raise UnknownModelError(model, sorted(self.table.models)) from None

    def cost_usd(self, model: str, usage: Usage) -> float:
        p = self.price(model)
        return (
            usage.input_tokens * p.input
            + usage.output_tokens * p.output
            + usage.cache_write_tokens * p.cache_write
            + usage.cache_read_tokens * p.cache_read
        ) / MILLION

    def cost_eur(self, model: str, usage: Usage) -> float:
        return self.cost_usd(model, usage) * self.eur_per_usd

    def estimate_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Stima preventiva senza cache: token in ingresso e in uscita a prezzo pieno."""
        return self.cost_usd(model, Usage(input_tokens=input_tokens, output_tokens=output_tokens))


def default_pricing(eur_per_usd: float = 1.0) -> Pricing:
    return Pricing(load_prices(), eur_per_usd)
