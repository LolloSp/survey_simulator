"""Impronta delle richieste, cache su disco, prezzi, client finto."""

from pathlib import Path

import pytest

from synthsurvey.llm import (
    FakeLLMClient,
    LLMError,
    LLMRequest,
    LLMResponse,
    Message,
    ResponseCache,
    UnknownModelError,
    Usage,
    default_pricing,
    fill_schema,
    load_prices,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "enum": ["a", "b"]},
        "score": {"type": "integer", "minimum": 1},
        "tags": {"type": "array", "items": {"type": "string"}},
        "sure": {"type": "boolean"},
    },
    "required": ["answer", "score", "tags", "sure"],
    "additionalProperties": False,
}


def richiesta(**kw: object) -> LLMRequest:
    base: dict[str, object] = {
        "system": "Sei Maria.",
        "messages": (Message("user", "Quanto sei soddisfatta?"),),
        "schema": SCHEMA,
    }
    base.update(kw)
    return LLMRequest(**base)  # type: ignore[arg-type]


def test_impronta_dipende_da_contenuto_modello_e_variante() -> None:
    r = richiesta()
    assert r.fingerprint("anthropic", "m1") == richiesta().fingerprint("anthropic", "m1")
    assert r.fingerprint("anthropic", "m1") != r.fingerprint("anthropic", "m2")
    assert r.fingerprint("anthropic", "m1") != richiesta(variant="rep2").fingerprint(
        "anthropic", "m1"
    )
    assert r.fingerprint("anthropic", "m1") != richiesta(effort="high").fingerprint(
        "anthropic", "m1"
    )
    assert r.fingerprint("anthropic", "m1") != richiesta(schema=None).fingerprint("anthropic", "m1")
    # I metadati servono ai log e non entrano nell'impronta.
    assert r.fingerprint("fake", "x") == richiesta(metadata={"persona": "p1"}).fingerprint(
        "fake", "x"
    )
    assert len(r.fingerprint("fake", "x")) == 64


def test_cache_su_disco(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "cache")
    resp = LLMResponse(
        text='{"answer": "a"}',
        parsed={"answer": "a"},
        usage=Usage(10, 5, 3, 0),
        provider="fake",
        model="fake-1",
        latency_ms=12,
        stop_reason="end_turn",
        request_id="req_1",
    )
    assert cache.get("ab" * 32) is None
    assert cache.count() == 0
    path = cache.put("ab" * 32, resp)
    assert path.is_file() and path.parent.name == "ab"
    letto = cache.get("ab" * 32)
    assert letto is not None and letto.from_cache is True
    assert letto.parsed == {"answer": "a"} and letto.usage == Usage(10, 5, 3, 0)
    assert letto.request_id == "req_1"
    assert ("ab" * 32) in cache and cache.count() == 1


def test_prezzi() -> None:
    table = load_prices()
    assert "claude-opus-5-5" in table.models and table.currency == "USD"
    pricing = default_pricing(eur_per_usd=0.5)
    usage = Usage(
        input_tokens=1_000_000,
        output_tokens=100_000,
        cache_read_tokens=500_000,
        cache_write_tokens=0,
    )
    opus = table.models["claude-opus-5-5"]
    atteso = opus.input + 0.1 * opus.output + 0.5 * opus.cache_read
    assert pricing.cost_usd("claude-opus-5-5", usage) == pytest.approx(atteso)
    assert pricing.cost_eur("claude-opus-5-5", usage) == pytest.approx(atteso * 0.5)
    assert pricing.estimate_usd("claude-haiku-5-5", 1_000_000, 0) == pytest.approx(0.10)
    assert pricing.cost_usd("fake-1", usage) == 0.0
    with pytest.raises(UnknownModelError, match="assente"):
        pricing.cost_usd("gpt-5", usage)


def test_riempimento_schema() -> None:
    valore = fill_schema(SCHEMA)
    assert valore == {"answer": "a", "score": 1, "tags": ["risposta di prova"], "sure": False}
    assert fill_schema({"type": "string"}) == "risposta di prova"
    assert fill_schema({"type": "number", "minimum": 2.5}) == 2.5


async def test_client_finto_default_e_responder() -> None:
    fake = FakeLLMClient()
    resp = await fake.complete(richiesta())
    assert resp.parsed == fill_schema(SCHEMA) and resp.provider == "fake"
    assert resp.usage.input_tokens > 0 and resp.usage.output_tokens > 0
    assert resp.usage.cache_read_tokens == 0, "prima chiamata: niente cache"
    resp2 = await fake.complete(richiesta())
    assert resp2.usage.cache_read_tokens > 0
    assert len(fake.requests) == 2

    scripted = FakeLLMClient(
        responder=lambda r: {"answer": "b", "score": 7, "tags": [], "sure": True}
    )
    assert (await scripted.complete(richiesta())).parsed == {
        "answer": "b",
        "score": 7,
        "tags": [],
        "sure": True,
    }
    testo = FakeLLMClient(responder=lambda r: "ciao")
    out = await testo.complete(richiesta(schema=None))
    assert out.text == "ciao" and out.parsed is None


async def test_client_finto_errori_e_rifiuti() -> None:
    rotto = FakeLLMClient(fail_times=2)
    with pytest.raises(LLMError):
        await rotto.complete(richiesta())
    with pytest.raises(LLMError):
        await rotto.complete(richiesta())
    assert (await rotto.complete(richiesta())).parsed is not None
    rifiuta = FakeLLMClient(refuse=True)
    resp = await rifiuta.complete(richiesta())
    assert resp.refused and resp.stop_reason == "refusal" and resp.parsed is None
