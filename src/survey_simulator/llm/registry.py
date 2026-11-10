"""Registro dei provider: dalla config al client concreto."""

from pathlib import Path

from survey_simulator.config.schema import ModelSpec, SurveySimulatorConfig
from survey_simulator.llm.cache import ResponseCache
from survey_simulator.llm.client import LLMClient, LLMError
from survey_simulator.llm.fake import FakeLLMClient
from survey_simulator.llm.pool import LLMPool
from survey_simulator.llm.pricing import Pricing, default_pricing


def make_client(spec: ModelSpec, config: SurveySimulatorConfig) -> LLMClient:
    """Client per un modello della config; le chiavi vengono solo dall'ambiente."""
    if spec.provider == "fake":
        return FakeLLMClient(spec.model)
    if spec.provider == "anthropic":
        from survey_simulator.llm.anthropic_client import AnthropicClient

        return AnthropicClient(
            spec.model,
            timeout_s=config.engine.timeout_s,
            # Haiku non ha fallback lato server sui rifiuti.
            use_fallbacks=not spec.model.startswith("claude-haiku"),
        )
    if spec.provider == "openai":
        from survey_simulator.llm.openai_client import OpenAIClient

        return OpenAIClient(
            spec.model, timeout_s=config.engine.timeout_s, temperature=config.engine.temperature
        )
    if spec.provider == "session":
        from survey_simulator.llm.session_client import SessionClient, SessionMailbox

        return SessionClient(SessionMailbox(session_mailbox_dir(config)), spec.model)
    raise LLMError(f"provider '{spec.provider}' sconosciuto")


def cache_dir_for(config: SurveySimulatorConfig) -> Path:
    return config.engine.cache_dir or (config.output.dir / ".cache")


def session_mailbox_dir(config: SurveySimulatorConfig) -> Path:
    """Cassetta delle richieste del provider `session` (M14)."""
    return cache_dir_for(config) / "session"


def make_pool(
    spec: ModelSpec,
    config: SurveySimulatorConfig,
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
