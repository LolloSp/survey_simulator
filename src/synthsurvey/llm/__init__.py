"""Livello LLM: client astratto, adapter, cache su disco, pool con limiti, costi."""

from synthsurvey.llm.cache import ResponseCache
from synthsurvey.llm.client import (
    LLMClient,
    LLMError,
    LLMRequest,
    LLMResponse,
    Message,
    SchemaError,
    Usage,
)
from synthsurvey.llm.fake import FakeLLMClient, fill_schema
from synthsurvey.llm.pool import LLMPool, PoolStats
from synthsurvey.llm.pricing import (
    PriceTable,
    Pricing,
    UnknownModelError,
    default_pricing,
    load_prices,
)
from synthsurvey.llm.registry import cache_dir_for, make_client, make_pool

__all__ = [
    "FakeLLMClient",
    "LLMClient",
    "LLMError",
    "LLMPool",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "PoolStats",
    "PriceTable",
    "Pricing",
    "ResponseCache",
    "SchemaError",
    "UnknownModelError",
    "Usage",
    "cache_dir_for",
    "default_pricing",
    "fill_schema",
    "load_prices",
    "make_client",
    "make_pool",
]
