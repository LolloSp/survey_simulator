"""Livello LLM: client astratto, adapter, cache su disco, pool con limiti, costi."""

from survey_simulator.llm.cache import ResponseCache
from survey_simulator.llm.client import (
    LLMClient,
    LLMError,
    LLMRequest,
    LLMResponse,
    Message,
    SchemaError,
    Usage,
)
from survey_simulator.llm.fake import FakeLLMClient, fill_schema
from survey_simulator.llm.pool import LLMPool, PoolStats
from survey_simulator.llm.pricing import (
    PriceTable,
    Pricing,
    UnknownModelError,
    default_pricing,
    load_prices,
)
from survey_simulator.llm.registry import cache_dir_for, make_client, make_pool, session_mailbox_dir
from survey_simulator.llm.session_client import (
    AwaitingAnswersError,
    PendingRequest,
    SessionClient,
    SessionMailbox,
    pending_markdown,
)

__all__ = [
    "AwaitingAnswersError",
    "FakeLLMClient",
    "LLMClient",
    "LLMError",
    "LLMPool",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "PendingRequest",
    "PoolStats",
    "PriceTable",
    "Pricing",
    "ResponseCache",
    "SchemaError",
    "SessionClient",
    "SessionMailbox",
    "UnknownModelError",
    "Usage",
    "cache_dir_for",
    "default_pricing",
    "fill_schema",
    "load_prices",
    "make_client",
    "make_pool",
    "pending_markdown",
    "session_mailbox_dir",
]
