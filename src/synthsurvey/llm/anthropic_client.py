"""Adapter per l'API Anthropic (SDK ufficiale `anthropic`, client asincrono).

Scelte fisse: risposte strutturate con `output_config.format` validate contro
lo schema, profondità di ragionamento con `output_config.effort`, prompt
caching del system prompt, fallback lato server sui rifiuti di sicurezza
(`fallbacks="default"`), nessun parametro di campionamento (i modelli Claude
attuali lo rifiutano). La chiave arriva solo dall'ambiente
(`ANTHROPIC_API_KEY`), mai dalla configurazione.
"""

import json
import logging
import time
from typing import Any

import anthropic
import jsonschema

from synthsurvey.llm.client import LLMClient, LLMError, LLMRequest, LLMResponse, SchemaError, Usage

FALLBACK_BETA = "server-side-fallback-2026-07-01"
log = logging.getLogger(__name__)


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        max_retries: int = 3,
        timeout_s: float = 120.0,
        schema_retries: int = 1,
        use_fallbacks: bool = True,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.model = model
        self.schema_retries = max(0, schema_retries)
        self.use_fallbacks = use_fallbacks
        self._client = client or anthropic.AsyncAnthropic(
            api_key=api_key, max_retries=max_retries, timeout=timeout_s
        )

    def _build_kwargs(self, request: LLMRequest) -> dict[str, Any]:
        system: Any = request.system
        if request.cache_system:
            system = [
                {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
            ]
        output_config: dict[str, Any] = {"effort": request.effort}
        if request.schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.schema}
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "output_config": output_config,
        }
        if self.use_fallbacks:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        return kwargs

    async def complete(self, request: LLMRequest) -> LLMResponse:
        kwargs = self._build_kwargs(request)
        ultimo: SchemaError | None = None
        for attempt in range(1, self.schema_retries + 2):
            t0 = time.perf_counter()
            try:
                resp = await self._client.beta.messages.create(**kwargs)
            except anthropic.APIStatusError as exc:
                raise LLMError(f"API Anthropic {exc.status_code}: {exc.message}") from exc
            except anthropic.APIConnectionError as exc:
                raise LLMError(f"connessione all'API Anthropic fallita: {exc}") from exc
            latency_ms = int((time.perf_counter() - t0) * 1000)
            text = "".join(getattr(b, "text", "") for b in resp.content if b.type == "text")
            stop_reason = str(resp.stop_reason)
            refused = stop_reason == "refusal"
            u = resp.usage
            usage = Usage(
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            )
            parsed: dict[str, Any] | None = None
            if request.schema is not None and not refused:
                try:
                    parsed = json.loads(text)
                    jsonschema.validate(parsed, request.schema)
                except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
                    ultimo = SchemaError(f"risposta non conforme allo schema: {exc}")
                    if attempt <= self.schema_retries:
                        log.warning(
                            "risposta non conforme allo schema, nuovo tentativo %d", attempt + 1
                        )
                        continue
                    raise ultimo from exc
            if stop_reason == "max_tokens":
                log.warning("risposta troncata a max_tokens=%d", request.max_tokens)
            return LLMResponse(
                text=text,
                parsed=parsed,
                usage=usage,
                provider=self.provider,
                model=str(getattr(resp, "model", self.model)),
                latency_ms=latency_ms,
                stop_reason=stop_reason,
                refused=refused,
                request_id=getattr(resp, "_request_id", None),
                attempts=attempt,
            )
        raise ultimo or LLMError("nessuna risposta")

    async def aclose(self) -> None:
        await self._client.close()
