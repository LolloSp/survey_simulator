"""Client LLM finto per i test e per i run a secco: nessuna chiamata reale.

Le risposte vengono da un `responder` (funzione della richiesta) oppure, se
assente, da un generatore che riempie lo schema richiesto con valori
plausibili. Registra ogni richiesta ricevuta e può simulare errori e latenza.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

from synthsurvey.llm.client import LLMClient, LLMError, LLMRequest, LLMResponse, Usage

Responder = Callable[[LLMRequest], str | dict[str, Any]]


def fill_schema(schema: dict[str, Any]) -> Any:
    """Valore di esempio conforme a uno schema JSON (object, array, enum, tipi base)."""
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    t = schema.get("type")
    if isinstance(t, list):
        t = t[0]
    if t == "object":
        props = schema.get("properties", {})
        required = schema.get("required", list(props))
        return {k: fill_schema(v) for k, v in props.items() if k in required}
    if t == "array":
        items = schema.get("items", {"type": "string"})
        n = schema.get("minItems", 1)
        return [fill_schema(items) for _ in range(n)]
    if t == "integer":
        return int(schema.get("minimum", 0))
    if t == "number":
        return float(schema.get("minimum", 0))
    if t == "boolean":
        return False
    if t == "null":
        return None
    return "risposta di prova"


class FakeLLMClient(LLMClient):
    provider = "fake"

    def __init__(
        self,
        model: str = "fake-1",
        responder: Responder | None = None,
        *,
        latency_ms: int = 0,
        fail_times: int = 0,
        refuse: bool = False,
        tokens_per_char: float = 0.25,
    ) -> None:
        self.model = model
        self.responder = responder
        self.latency_ms = latency_ms
        self.fail_times = fail_times
        self.refuse = refuse
        self.tokens_per_char = tokens_per_char
        self.requests: list[LLMRequest] = []
        self.calls = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        self.calls += 1
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise LLMError("errore simulato del provider")
        if self.refuse:
            return LLMResponse(
                text="",
                parsed=None,
                usage=Usage(input_tokens=self._tokens(request), output_tokens=0),
                provider=self.provider,
                model=self.model,
                latency_ms=self.latency_ms,
                stop_reason="refusal",
                refused=True,
            )
        if self.responder is not None:
            out = self.responder(request)
        elif request.schema is not None:
            out = fill_schema(request.schema)
        else:
            out = "risposta di prova"
        if isinstance(out, dict):
            text = json.dumps(out, ensure_ascii=False)
            parsed: dict[str, Any] | None = out
        else:
            text = str(out)
            parsed = None
            if request.schema is not None:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
        return LLMResponse(
            text=text,
            parsed=parsed,
            usage=Usage(
                input_tokens=self._tokens(request),
                output_tokens=max(1, int(len(text) * self.tokens_per_char)),
                cache_read_tokens=int(len(request.system) * self.tokens_per_char)
                if request.cache_system and self.calls > 1
                else 0,
            ),
            provider=self.provider,
            model=self.model,
            latency_ms=self.latency_ms,
            stop_reason="end_turn",
        )

    def _tokens(self, request: LLMRequest) -> int:
        chars = len(request.system) + sum(len(m.content) for m in request.messages)
        return max(1, int(chars * self.tokens_per_char))
