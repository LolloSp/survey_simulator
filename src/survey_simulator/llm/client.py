"""Interfaccia astratta verso i provider LLM.

Il resto del sistema parla solo con `LLMClient`: una richiesta (`LLMRequest`)
e una risposta (`LLMResponse`) indipendenti dal provider. L'adapter concreto
sta in un modulo per provider; i test usano sempre `FakeLLMClient`.
"""

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Role = Literal["user", "assistant"]
Effort = Literal["low", "medium", "high"]


class LLMError(Exception):
    """Errore del provider non recuperabile dopo i tentativi previsti."""


class SchemaError(LLMError):
    """La risposta non rispetta lo schema JSON richiesto."""


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class LLMRequest:
    """Richiesta indipendente dal provider.

    `variant` distingue richieste altrimenti identiche (ad esempio le repliche
    di un'intervista) così la cache non le confonde. `metadata` serve ai log e
    non entra nell'impronta.
    """

    system: str
    messages: tuple[Message, ...]
    schema: dict[str, Any] | None = None  # JSON Schema della risposta strutturata
    max_tokens: int = 1024
    effort: Effort = "low"
    variant: str = ""
    cache_system: bool = True  # prompt caching del system prompt lato provider
    metadata: dict[str, str] = field(default_factory=dict)

    def fingerprint(self, provider: str, model: str) -> str:
        """Hash SHA-256 del contenuto che determina la risposta."""
        payload = {
            "provider": provider,
            "model": model,
            "system": self.system,
            "messages": [asdict(m) for m in self.messages],
            "schema": self.schema,
            "max_tokens": self.max_tokens,
            "effort": self.effort,
            "variant": self.variant,
        }
        canon = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )


@dataclass(frozen=True)
class LLMResponse:
    text: str
    parsed: dict[str, Any] | None
    usage: Usage
    provider: str
    model: str
    latency_ms: int
    stop_reason: str
    refused: bool = False
    request_id: str | None = None
    attempts: int = 1
    from_cache: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMResponse":
        usage = Usage(**data["usage"])
        return cls(**{**data, "usage": usage})


class LLMClient(ABC):
    """Contratto minimo di un provider: una richiesta, una risposta, asincrono."""

    provider: str
    model: str

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse: ...

    async def aclose(self) -> None:
        return None
