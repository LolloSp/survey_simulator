"""Adapter per l'API OpenAI (SDK ufficiale `openai`, client asincrono, Chat Completions).

Scelte fisse: risposte strutturate con `response_format` di tipo
`json_schema` in modalità `strict`, validate contro lo schema con un
secondo tentativo; `reasoning_effort` solo per i modelli che ragionano
(serie `o` e `gpt-5`); temperatura solo se indicata in configurazione e
solo per i modelli che la accettano. La chiave arriva solo dall'ambiente
(`OPENAI_API_KEY`), mai dalla configurazione. Il prompt caching è
automatico lato server: i token letti dalla cache arrivano in
`prompt_tokens_details.cached_tokens`.
"""

import json
import logging
import time
from typing import Any

import jsonschema
import openai

from synthsurvey.llm.client import LLMClient, LLMError, LLMRequest, LLMResponse, SchemaError, Usage

log = logging.getLogger(__name__)
REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")


def supports_reasoning_effort(model: str) -> bool:
    return model.startswith(REASONING_PREFIXES)


class OpenAIClient(LLMClient):
    provider = "openai"

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        max_retries: int = 3,
        timeout_s: float = 120.0,
        schema_retries: int = 1,
        temperature: float | None = None,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        self.schema_retries = max(0, schema_retries)
        self.temperature = temperature
        if client is not None:
            self._client = client
            return
        try:
            self._client = openai.AsyncOpenAI(
                api_key=api_key, max_retries=max_retries, timeout=timeout_s
            )
        except openai.OpenAIError as exc:
            raise LLMError(
                "chiave OpenAI assente: impostare OPENAI_API_KEY nell'ambiente o in .env"
            ) from exc

    def _build_kwargs(self, request: LLMRequest) -> dict[str, Any]:
        messages: list[dict[str, str]] = [{"role": "system", "content": request.system}]
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": request.max_tokens,
        }
        if request.schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "risposta", "schema": request.schema, "strict": True},
            }
        if supports_reasoning_effort(self.model):
            kwargs["reasoning_effort"] = request.effort
        elif self.temperature is not None:
            kwargs["temperature"] = self.temperature
        return kwargs

    async def complete(self, request: LLMRequest) -> LLMResponse:
        kwargs = self._build_kwargs(request)
        ultimo: Exception | None = None
        for attempt in range(1, self.schema_retries + 2):
            inizio = time.perf_counter()
            try:
                completion = await self._client.chat.completions.create(**kwargs)
            except openai.APIStatusError as exc:
                raise LLMError(f"OpenAI {exc.status_code}: {exc.message}") from exc
            except openai.APIConnectionError as exc:
                raise LLMError(f"OpenAI non raggiungibile: {exc}") from exc
            except openai.OpenAIError as exc:
                raise LLMError(f"OpenAI: {exc}") from exc
            latency_ms = int((time.perf_counter() - inizio) * 1000)
            scelta = completion.choices[0] if completion.choices else None
            messaggio = scelta.message if scelta is not None else None
            testo = (messaggio.content or "") if messaggio is not None else ""
            rifiuto = getattr(messaggio, "refusal", None) if messaggio is not None else None
            stop = str(scelta.finish_reason) if scelta is not None else "unknown"
            refused = bool(rifiuto) or stop == "content_filter"
            usage = _usage(completion.usage)
            parsed: dict[str, Any] | None = None
            if request.schema is not None and not refused:
                try:
                    parsed = json.loads(testo)
                    jsonschema.validate(parsed, request.schema)
                except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
                    ultimo = SchemaError(f"risposta non conforme allo schema: {exc}")
                    if attempt <= self.schema_retries:
                        log.warning(
                            "risposta non conforme allo schema, nuovo tentativo %d", attempt + 1
                        )
                        continue
                    raise ultimo from exc
            return LLMResponse(
                text=rifiuto or testo if refused else testo,
                parsed=parsed,
                usage=usage,
                provider=self.provider,
                model=str(getattr(completion, "model", self.model)),
                latency_ms=latency_ms,
                stop_reason=stop,
                refused=refused,
                request_id=getattr(completion, "_request_id", None),
                attempts=attempt,
            )
        raise ultimo or LLMError("nessuna risposta")  # pragma: no cover

    async def aclose(self) -> None:
        await self._client.close()


def _usage(u: Any) -> Usage:
    if u is None:
        return Usage()
    dettagli = getattr(u, "prompt_tokens_details", None)
    cached = int(getattr(dettagli, "cached_tokens", 0) or 0) if dettagli is not None else 0
    prompt = int(getattr(u, "prompt_tokens", 0) or 0)
    return Usage(
        input_tokens=max(0, prompt - cached),
        output_tokens=int(getattr(u, "completion_tokens", 0) or 0),
        cache_read_tokens=cached,
        cache_write_tokens=0,
    )
