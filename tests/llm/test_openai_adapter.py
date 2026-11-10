"""Adapter OpenAI con l'SDK simulato: nessuna chiamata reale."""

from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from survey_simulator.llm import LLMError, LLMRequest, Message, SchemaError
from survey_simulator.llm.openai_client import OpenAIClient, supports_reasoning_effort

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "score": {"type": "integer"}},
    "required": ["answer", "score"],
    "additionalProperties": False,
}


class FakeCompletions:
    def __init__(self, risposte: list[Any]) -> None:
        self.risposte = list(risposte)
        self.chiamate: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.chiamate.append(kwargs)
        r = self.risposte.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def fake_client(risposte: list[Any]) -> tuple[Any, FakeCompletions]:
    completions = FakeCompletions(risposte)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    async def close() -> None:
        return None

    client.close = close
    return client, completions


def risposta(
    content: str | None, *, refusal: str | None = None, finish: str = "stop", cached: int = 0
) -> Any:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, refusal=refusal), finish_reason=finish
            )
        ],
        model="gpt-5",
        usage=SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=15,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
        ),
        _request_id="req_x",
    )


def richiesta(**kw: Any) -> LLMRequest:
    base: dict[str, Any] = {
        "system": "Sei Giulia.",
        "messages": (Message("user", "Quanto sei soddisfatta?"),),
        "schema": SCHEMA,
        "max_tokens": 200,
        "effort": "medium",
    }
    base.update(kw)
    return LLMRequest(**base)


async def test_risposta_strutturata_e_parametri() -> None:
    client, comp = fake_client([risposta('{"answer": "molto", "score": 8}', cached=100)])
    adapter = OpenAIClient("gpt-5", client=client, temperature=0.7)
    out = await adapter.complete(richiesta())
    assert out.parsed == {"answer": "molto", "score": 8} and out.provider == "openai"
    assert out.usage.input_tokens == 20 and out.usage.cache_read_tokens == 100
    assert out.usage.output_tokens == 15 and out.usage.cache_write_tokens == 0
    assert out.model == "gpt-5" and out.request_id == "req_x" and not out.refused
    kw = comp.chiamate[0]
    assert kw["model"] == "gpt-5" and kw["max_completion_tokens"] == 200
    assert kw["messages"][0] == {"role": "system", "content": "Sei Giulia."}
    assert kw["messages"][1] == {"role": "user", "content": "Quanto sei soddisfatta?"}
    assert kw["response_format"]["type"] == "json_schema"
    assert kw["response_format"]["json_schema"]["strict"] is True
    assert kw["response_format"]["json_schema"]["schema"] == SCHEMA
    assert kw["reasoning_effort"] == "medium" and "temperature" not in kw, "gpt-5 ragiona"


async def test_temperatura_solo_per_modelli_senza_ragionamento() -> None:
    client, comp = fake_client([risposta("ciao")])
    adapter = OpenAIClient("gpt-4.1", client=client, temperature=0.4)
    out = await adapter.complete(richiesta(schema=None))
    assert out.text == "ciao" and out.parsed is None
    kw = comp.chiamate[0]
    assert kw["temperature"] == 0.4 and "reasoning_effort" not in kw
    assert "response_format" not in kw
    assert supports_reasoning_effort("o3-mini") and not supports_reasoning_effort("gpt-4o")
    senza, comp2 = fake_client([risposta("x")])
    await OpenAIClient("gpt-4.1", client=senza).complete(richiesta(schema=None))
    assert "temperature" not in comp2.chiamate[0]


async def test_schema_non_rispettato_riprova_poi_errore() -> None:
    client, comp = fake_client(
        [risposta('{"answer": 1}'), risposta('{"answer": "ok", "score": 2}')]
    )
    out = await OpenAIClient("gpt-5", client=client).complete(richiesta())
    assert out.parsed == {"answer": "ok", "score": 2} and out.attempts == 2
    assert len(comp.chiamate) == 2
    client, _ = fake_client([risposta("non json"), risposta("ancora no")])
    with pytest.raises(SchemaError):
        await OpenAIClient("gpt-5", client=client).complete(richiesta())


async def test_rifiuto_e_filtro() -> None:
    client, _ = fake_client([risposta(None, refusal="Non posso aiutarti.")])
    out = await OpenAIClient("gpt-5", client=client).complete(richiesta())
    assert out.refused and out.parsed is None and out.text == "Non posso aiutarti."
    client, _ = fake_client([risposta("", finish="content_filter")])
    out = await OpenAIClient("gpt-5", client=client).complete(richiesta())
    assert out.refused and out.stop_reason == "content_filter"


async def test_errori_del_provider_tradotti() -> None:
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp = httpx.Response(429, request=req, json={"error": {"message": "rate"}})
    status = openai.RateLimitError("troppe richieste", response=resp, body=None)
    client, _ = fake_client([status])
    with pytest.raises(LLMError, match="OpenAI 429"):
        await OpenAIClient("gpt-5", client=client).complete(richiesta())
    conn = openai.APIConnectionError(request=req)
    client, _ = fake_client([conn])
    with pytest.raises(LLMError, match="non raggiungibile"):
        await OpenAIClient("gpt-5", client=client).complete(richiesta())
    await OpenAIClient("gpt-5", client=client).aclose()


def test_registry_costruisce_il_client_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    from survey_simulator.config import parse_config
    from survey_simulator.llm import make_client
    from tests.config.conftest import config_base

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    raw = config_base()
    raw["engine"]["models"] = [{"provider": "openai", "model": "gpt-5-mini"}]
    raw["engine"]["temperature"] = 0.5
    cfg = parse_config(raw)
    client = make_client(cfg.engine.models[0], cfg)
    assert isinstance(client, OpenAIClient) and client.model == "gpt-5-mini"
    assert client.temperature == 0.5
