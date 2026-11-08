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
from synthsurvey.llm.registry import cache_dir_for, make_client, make_pool, session_mailbox_dir
from synthsurvey.llm.session_client import (
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
