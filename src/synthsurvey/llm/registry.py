"""Registro dei provider: dalla config al client concreto."""

from pathlib import Path

from synthsurvey.config.schema import ModelSpec, SynthSurveyConfig
from synthsurvey.llm.cache import ResponseCache
from synthsurvey.llm.client import LLMClient, LLMError
from synthsurvey.llm.fake import FakeLLMClient
from synthsurvey.llm.pool import LLMPool
from synthsurvey.llm.pricing import Pricing, default_pricing


def make_client(spec: ModelSpec, config: SynthSurveyConfig) -> LLMClient:
    """Client per un modello della config; le chiavi vengono solo dall'ambiente."""
    if spec.provider == "fake":
        return FakeLLMClient(spec.model)
    if spec.provider == "anthropic":
        from synthsurvey.llm.anthropic_client import AnthropicClient

        return AnthropicClient(
            spec.model,
            timeout_s=config.engine.timeout_s,
            # Haiku non ha fallback lato server sui rifiuti.
            use_fallbacks=not spec.model.startswith("claude-haiku"),
        )
    if spec.provider == "openai":
        from synthsurvey.llm.openai_client import OpenAIClient

        return OpenAIClient(
            spec.model, timeout_s=config.engine.timeout_s, temperature=config.engine.temperature
        )
    raise LLMError(f"provider '{spec.provider}' sconosciuto")


def cache_dir_for(config: SynthSurveyConfig) -> Path:
    return config.engine.cache_dir or (config.output.dir / ".cache")


def make_pool(
    spec: ModelSpec,
    config: SynthSurveyConfig,
    *,
    pricing: Pricing | None = None,
    use_cache: bool = True,
) -> LLMPool:
    """Pool pronto all'uso per un modello: client, cache su disco, prezzi, concorrenza."""
    client = make_client(spec, config)
    cache = ResponseCache(cache_dir_for(config)) if use_cache else None
    return LLMPool(
        client,
        cache=cache,
        pricing=pricing if pricing is not None else default_pricing(config.engine.eur_per_usd),
        concurrency=config.engine.concurrency,
        timeout_s=config.engine.timeout_s,
    )
