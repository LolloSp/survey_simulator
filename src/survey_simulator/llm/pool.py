"""Pool di chiamate: cache, limite di concorrenza, timeout, contatori e costi."""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field

from survey_simulator.llm.cache import ResponseCache
from survey_simulator.llm.client import LLMClient, LLMError, LLMRequest, LLMResponse, Usage
from survey_simulator.llm.pricing import Pricing


@dataclass
class PoolStats:
    requests: int = 0
    cache_hits: int = 0
    calls: int = 0
    errors: int = 0
    refusals: int = 0
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    latency_ms_total: int = 0

    @property
    def cache_hit_rate(self) -> float:
        return self.cache_hits / self.requests if self.requests else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "requests": self.requests,
            "cache_hits": self.cache_hits,
            "calls": self.calls,
            "errors": self.errors,
            "refusals": self.refusals,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "cache_read_tokens": self.usage.cache_read_tokens,
            "cache_write_tokens": self.usage.cache_write_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms_mean": round(self.latency_ms_total / self.calls) if self.calls else 0,
        }


class LLMPool:
    """Esegue le richieste su un client con cache, semaforo di concorrenza e timeout.

    Il costo è conteggiato solo per le chiamate reali; le risposte dalla cache
    contano come richieste ma non come chiamate.
    """

    def __init__(
        self,
        client: LLMClient,
        *,
        cache: ResponseCache | None = None,
        pricing: Pricing | None = None,
        concurrency: int = 4,
        timeout_s: float = 120.0,
    ) -> None:
        self.client = client
        self.cache = cache
        self.pricing = pricing
        self.concurrency = max(1, concurrency)
        self.timeout_s = timeout_s
        self.stats = PoolStats()
        self._semaphore: asyncio.Semaphore | None = None
        self._lock: asyncio.Lock | None = None

    def _sync(self) -> tuple[asyncio.Semaphore, asyncio.Lock]:
        if self._semaphore is None or self._lock is None:
            self._semaphore = asyncio.Semaphore(self.concurrency)
            self._lock = asyncio.Lock()
        return self._semaphore, self._lock

    async def complete(self, request: LLMRequest) -> LLMResponse:
        key = request.fingerprint(self.client.provider, self.client.model)
        semaphore, lock = self._sync()
        async with lock:
            self.stats.requests += 1
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                async with lock:
                    self.stats.cache_hits += 1
                return hit
        async with semaphore:
            try:
                response = await asyncio.wait_for(self.client.complete(request), self.timeout_s)
            except TimeoutError as exc:
                async with lock:
                    self.stats.errors += 1
                raise LLMError(f"timeout dopo {self.timeout_s:g} s") from exc
            except LLMError:
                async with lock:
                    self.stats.errors += 1
                raise
        async with lock:
            self.stats.calls += 1
            self.stats.usage = self.stats.usage + response.usage
            self.stats.latency_ms_total += response.latency_ms
            if response.refused:
                self.stats.refusals += 1
            if self.pricing is not None:
                self.stats.cost_usd += self.pricing.cost_usd(response.model, response.usage)
        if self.cache is not None and not response.refused:
            self.cache.put(key, response)
        return response

    async def gather(self, requests: Iterable[LLMRequest]) -> list[LLMResponse]:
        """Esegue le richieste in parallelo entro il limite di concorrenza, nell'ordine dato."""
        return list(await asyncio.gather(*(self.complete(r) for r in requests)))
