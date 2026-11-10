"""Adapter Anthropic con l'SDK simulato: nessuna chiamata reale."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2 as httpx
import pytest

from survey_simulator.llm import LLMError, LLMRequest, Message, SchemaError
from survey_simulator.llm.anthropic_client import FALLBACK_BETA, AnthropicClient

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "score": {"type": "integer"}},
    "required": ["answer", "score"],
    "additionalProperties": False,
}


class FakeMessages:
    """Sostituisce `client.beta.messages`: registra le chiamate, risponde con uno script."""

    def __init__(self, risposte: list[Any]) -> None:
        self.risposte = list(risposte)
        self.chiamate: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.chiamate.append(kwargs)
        r = self.risposte.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def risposta(text: str, stop: str = "end_turn", cache_read: int = 0, cache_write: int = 0) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop,
        model="claude-opus-5-5",
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_write,
        ),
        _request_id="req_abc",
    )


def client_con(risposte: list[Any], **kw: Any) -> tuple[AnthropicClient, FakeMessages]:
    finto = FakeMessages(risposte)
    sdk = SimpleNamespace(beta=SimpleNamespace(messages=finto), close=_close)
    c = AnthropicClient("claude-opus-5-5", client=sdk, **kw)  # type: ignore[arg-type]
    return c, finto


async def _close() -> None:
    return None


def richiesta(**kw: Any) -> LLMRequest:
    base: dict[str, Any] = {
        "system": "Sei Giulia.",
        "messages": (Message("user", "Quanto sei soddisfatta?"),),
        "schema": SCHEMA,
        "effort": "medium",
        "max_tokens": 256,
    }
    base.update(kw)
    return LLMRequest(**base)


async def test_richiesta_strutturata_e_parametri() -> None:
    c, finto = client_con(
        [risposta('{"answer": "molto", "score": 8}', cache_read=40, cache_write=0)]
    )
    resp = await c.complete(richiesta())
    assert resp.parsed == {"answer": "molto", "score": 8}
    assert resp.usage.input_tokens == 100 and resp.usage.cache_read_tokens == 40
    assert resp.request_id == "req_abc" and resp.attempts == 1 and not resp.refused
    kw = finto.chiamate[0]
    assert kw["model"] == "claude-opus-5-5" and kw["max_tokens"] == 256
    assert kw["output_config"] == {
        "effort": "medium",
        "format": {"type": "json_schema", "schema": SCHEMA},
    }
    assert (
        kw["system"][0]["cache_control"] == {"type": "ephemeral"}
        and kw["system"][0]["text"] == "Sei Giulia."
    )
    assert kw["betas"] == [FALLBACK_BETA] and kw["fallbacks"] == "default"
    assert kw["messages"] == [{"role": "user", "content": "Quanto sei soddisfatta?"}]
    assert "temperature" not in kw and "thinking" not in kw


async def test_senza_schema_senza_cache_senza_fallback() -> None:
    c, finto = client_con([risposta("ciao")], use_fallbacks=False)
    resp = await c.complete(richiesta(schema=None, cache_system=False))
    assert resp.text == "ciao" and resp.parsed is None
    kw = finto.chiamate[0]
    assert kw["system"] == "Sei Giulia." and "format" not in kw["output_config"]
    assert "betas" not in kw and "fallbacks" not in kw


async def test_risposta_non_conforme_viene_richiesta_una_volta() -> None:
    c, finto = client_con([risposta("non json"), risposta('{"answer": "ok", "score": 3}')])
    resp = await c.complete(richiesta())
    assert resp.parsed == {"answer": "ok", "score": 3} and resp.attempts == 2
    assert len(finto.chiamate) == 2


async def test_risposta_non_conforme_due_volte_fallisce() -> None:
    c, _ = client_con([risposta('{"answer": "ok"}'), risposta('{"answer": 5, "score": "x"}')])
    with pytest.raises(SchemaError, match="schema"):
        await c.complete(richiesta())
    c2, _ = client_con([risposta("boh")], schema_retries=0)
    with pytest.raises(SchemaError):
        await c2.complete(richiesta())


async def test_rifiuto_e_troncamento() -> None:
    c, _ = client_con([risposta("", stop="refusal")])
    resp = await c.complete(richiesta())
    assert resp.refused and resp.parsed is None and resp.stop_reason == "refusal"
    c2, _ = client_con([risposta("testo lungo", stop="max_tokens")])
    out = await c2.complete(richiesta(schema=None))
    assert out.stop_reason == "max_tokens" and out.text == "testo lungo"


async def test_errori_sdk_diventano_llm_error() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    status = anthropic.APIStatusError(
        "server down", response=httpx.Response(503, request=request), body=None
    )
    c, _ = client_con([status])
    with pytest.raises(LLMError, match="503"):
        await c.complete(richiesta())
    conn = anthropic.APIConnectionError(request=request)
    c2, _ = client_con([conn])
    with pytest.raises(LLMError, match="connessione"):
        await c2.complete(richiesta())


async def test_chiusura() -> None:
    c, _ = client_con([])
    await c.aclose()
