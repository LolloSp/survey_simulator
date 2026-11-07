"""Pool: cache, concorrenza, timeout, errori, costi, registro dalla config."""

import asyncio
from pathlib import Path

import pytest

from synthsurvey.config import load_config, parse_config
from synthsurvey.llm import (
    FakeLLMClient,
    LLMError,
    LLMPool,
    LLMRequest,
    Message,
    ResponseCache,
    cache_dir_for,
    default_pricing,
    make_client,
    make_pool,
)
from synthsurvey.llm.anthropic_client import AnthropicClient
from tests.config.conftest import ESEMPI_DIR, config_base


def req(i: int, variant: str = "") -> LLMRequest:
    return LLMRequest(system="s", messages=(Message("user", f"domanda {i}"),), variant=variant)


async def test_cache_evita_la_seconda_chiamata(tmp_path: Path) -> None:
    fake = FakeLLMClient(responder=lambda r: "x")
    pool = LLMPool(fake, cache=ResponseCache(tmp_path), pricing=default_pricing())
    a = await pool.complete(req(1))
    b = await pool.complete(req(1))
    assert not a.from_cache and b.from_cache
    assert fake.calls == 1 and pool.stats.requests == 2 and pool.stats.cache_hits == 1
    assert pool.stats.cache_hit_rate == 0.5
    # Variante diversa: nuova chiamata.
    await pool.complete(req(1, variant="rep2"))
    assert fake.calls == 2


async def test_concorrenza_limitata() -> None:
    in_corso = 0
    massimo = 0

    class Lento(FakeLLMClient):
        async def complete(self, request: LLMRequest):  # type: ignore[override]
            nonlocal in_corso, massimo
            in_corso += 1
            massimo = max(massimo, in_corso)
            await asyncio.sleep(0.02)
            in_corso -= 1
            return await super().complete(request)

    pool = LLMPool(Lento(), concurrency=3)
    out = await pool.gather([req(i) for i in range(10)])
    assert len(out) == 10 and massimo == 3
    assert pool.stats.calls == 10


async def test_timeout_ed_errori() -> None:
    pool = LLMPool(FakeLLMClient(latency_ms=200), timeout_s=0.05)
    with pytest.raises(LLMError, match="timeout"):
        await pool.complete(req(1))
    assert pool.stats.errors == 1
    pool2 = LLMPool(FakeLLMClient(fail_times=1))
    with pytest.raises(LLMError):
        await pool2.complete(req(1))
    assert pool2.stats.errors == 1 and pool2.stats.calls == 0


async def test_rifiuti_non_in_cache(tmp_path: Path) -> None:
    pool = LLMPool(FakeLLMClient(refuse=True), cache=ResponseCache(tmp_path))
    resp = await pool.complete(req(1))
    assert resp.refused and pool.stats.refusals == 1
    assert (await pool.complete(req(1))).from_cache is False


async def test_costi_e_statistiche() -> None:
    pool = LLMPool(FakeLLMClient(), pricing=default_pricing())
    await pool.gather([req(i) for i in range(3)])
    d = pool.stats.as_dict()
    assert d["calls"] == 3 and d["cost_usd"] == 0.0 and d["input_tokens"] > 0
    assert d["latency_ms_mean"] == 0


def test_registro_dalla_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = config_base()
    raw["engine"]["models"] = [
        {"provider": "fake", "model": "fake-1"},
        {"provider": "anthropic", "model": "claude-haiku-5-5"},
        {"provider": "openai", "model": "gpt-5"},
    ]
    raw["engine"]["cache_dir"] = str(tmp_path / "c")
    cfg = parse_config(raw)
    assert isinstance(make_client(cfg.engine.models[0], cfg), FakeLLMClient)
    haiku = make_client(cfg.engine.models[1], cfg)
    assert isinstance(haiku, AnthropicClient) and haiku.use_fallbacks is False
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        make_client(cfg.engine.models[2], cfg)
    assert cache_dir_for(cfg) == tmp_path / "c"
    pool = make_pool(cfg.engine.models[0], cfg)
    assert pool.concurrency == cfg.engine.concurrency and pool.cache is not None
    assert make_pool(cfg.engine.models[0], cfg, use_cache=False).cache is None


def test_config_esempio_usa_opus_e_cache_di_default() -> None:
    cfg = load_config(ESEMPI_DIR / "mercato_100.yaml").config
    assert cfg.engine.models[0].model == "claude-opus-5-5"
    assert cfg.engine.effort == "low" and cfg.engine.temperature is None
    assert cache_dir_for(cfg) == cfg.output.dir / ".cache"


def test_provider_sconosciuto_e_temperatura_ignorata() -> None:
    raw = config_base()
    raw["engine"]["models"] = [{"provider": "mistral", "model": "x"}]
    with pytest.raises(Exception, match="sconosciuto"):
        parse_config(raw)
    raw = config_base()
    raw["engine"]["temperature"] = 0.8
    raw["engine"]["models"] = [{"provider": "anthropic", "model": "claude-opus-5-5"}]
    from synthsurvey.config import validate_config

    avvisi = validate_config(parse_config(raw))
    assert any(a.location == "engine.temperature" for a in avvisi)
