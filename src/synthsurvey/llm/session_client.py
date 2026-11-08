"""Provider `session` (M14): il modello è la sessione di Claude Code, via file.

Nessuna chiamata API. Ogni richiesta senza risposta viene scritta in
`<cassetta>/pending/<impronta>.json` e l'adapter solleva
`AwaitingAnswersError`: il runner sospende l'intervista e riparte quando
le risposte compaiono in `<cassetta>/answers/<impronta>.json`, depositate
con `synthsurvey session answer`. Le risposte sono validate contro lo
schema della richiesta prima di essere accettate.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

from synthsurvey.llm.client import LLMClient, LLMError, LLMRequest, LLMResponse, Usage

MODEL_NAME = "session"
CHARS_PER_TOKEN = 4


class AwaitingAnswersError(LLMError):
    """La richiesta è in attesa di una risposta dalla sessione."""

    def __init__(self, fingerprint: str, path: Path) -> None:
        self.fingerprint = fingerprint
        self.path = path
        super().__init__(f"richiesta in attesa di risposta dalla sessione: {path.name}")


@dataclass(frozen=True)
class PendingRequest:
    fingerprint: str
    system: str
    messages: list[dict[str, str]]
    schema: dict[str, Any] | None
    metadata: dict[str, str]
    variant: str

    @property
    def last_user_message(self) -> str:
        for m in reversed(self.messages):
            if m["role"] == "user":
                return m["content"]
        return ""


class SessionMailbox:
    """Cartelle `pending` e `answers` sotto la cache del progetto."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.pending_dir = root / "pending"
        self.answers_dir = root / "answers"

    def ensure(self) -> None:
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.answers_dir.mkdir(parents=True, exist_ok=True)

    def pending_path(self, fingerprint: str) -> Path:
        return self.pending_dir / f"{fingerprint}.json"

    def answer_path(self, fingerprint: str) -> Path:
        return self.answers_dir / f"{fingerprint}.json"

    def write_pending(self, request: LLMRequest, fingerprint: str) -> Path:
        self.ensure()
        path = self.pending_path(fingerprint)
        if not path.exists():
            payload = {
                "fingerprint": fingerprint,
                "system": request.system,
                "messages": [{"role": m.role, "content": m.content} for m in request.messages],
                "schema": request.schema,
                "metadata": dict(request.metadata),
                "variant": request.variant,
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def pending(self) -> list[PendingRequest]:
        if not self.pending_dir.is_dir():
            return []
        out = []
        for path in sorted(self.pending_dir.glob("*.json")):
            d = json.loads(path.read_text(encoding="utf-8"))
            out.append(
                PendingRequest(
                    fingerprint=d["fingerprint"],
                    system=d["system"],
                    messages=d["messages"],
                    schema=d.get("schema"),
                    metadata=d.get("metadata", {}),
                    variant=d.get("variant", ""),
                )
            )
        return out

    def read_answer(self, fingerprint: str) -> dict[str, Any] | None:
        path = self.answer_path(fingerprint)
        if not path.is_file():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def deposit(self, answers: dict[str, Any]) -> tuple[list[str], list[str]]:
        """Accetta `impronta -> risposta` (oggetto per gli schemi, testo altrimenti).

        Restituisce (accettate, errori). Una risposta non conforme allo schema
        della richiesta in attesa viene rifiutata con il motivo.
        """
        self.ensure()
        accettate: list[str] = []
        errori: list[str] = []
        for fp, risposta in answers.items():
            pending = self.pending_path(fp)
            schema: dict[str, Any] | None = None
            if pending.is_file():
                schema = json.loads(pending.read_text(encoding="utf-8")).get("schema")
            if schema is not None:
                if not isinstance(risposta, dict):
                    errori.append(f"{fp[:12]}: serve un oggetto JSON conforme allo schema")
                    continue
                try:
                    jsonschema.validate(risposta, schema)
                except jsonschema.ValidationError as exc:
                    errori.append(f"{fp[:12]}: non conforme allo schema: {exc.message}")
                    continue
                payload: dict[str, Any] = {
                    "parsed": risposta,
                    "text": json.dumps(risposta, ensure_ascii=False),
                }
            else:
                payload = {"parsed": None, "text": str(risposta)}
            self.answer_path(fp).write_text(
                json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            if pending.is_file():
                pending.unlink()
            accettate.append(fp)
        return accettate, errori

    def counts(self) -> tuple[int, int]:
        n_p = len(list(self.pending_dir.glob("*.json"))) if self.pending_dir.is_dir() else 0
        n_a = len(list(self.answers_dir.glob("*.json"))) if self.answers_dir.is_dir() else 0
        return n_p, n_a


def _tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


class SessionClient(LLMClient):
    provider = "session"

    def __init__(self, mailbox: SessionMailbox, model: str = MODEL_NAME) -> None:
        self.model = model
        self.mailbox = mailbox

    async def complete(self, request: LLMRequest) -> LLMResponse:
        fp = request.fingerprint(self.provider, self.model)
        risposta = self.mailbox.read_answer(fp)
        if risposta is None:
            path = self.mailbox.write_pending(request, fp)
            raise AwaitingAnswersError(fp, path)
        parsed = risposta.get("parsed")
        testo = str(risposta.get("text", ""))
        if request.schema is not None:
            try:
                jsonschema.validate(parsed, request.schema)
            except jsonschema.ValidationError as exc:
                raise LLMError(
                    f"risposta della sessione non conforme allo schema ({fp[:12]}): {exc.message}"
                ) from exc
        ingresso = _tokens(request.system) + sum(_tokens(m.content) for m in request.messages)
        return LLMResponse(
            text=testo,
            parsed=parsed if isinstance(parsed, dict) else None,
            usage=Usage(input_tokens=ingresso, output_tokens=_tokens(testo)),
            provider=self.provider,
            model=self.model,
            latency_ms=0,
            stop_reason="end_turn",
        )


def pending_markdown(requests: list[PendingRequest], *, full: bool = True) -> str:
    """Elenco leggibile delle richieste in attesa, per chi risponde nella sessione."""
    righe = [f"# Richieste in attesa: {len(requests)}", ""]
    for r in requests:
        meta = ", ".join(f"{k}={v}" for k, v in sorted(r.metadata.items()))
        righe.append(f"## {r.fingerprint}")
        righe.append(f"*{meta}*" if meta else "")
        if full:
            righe.append("")
            righe.append("### System")
            righe.append("")
            righe.append(r.system)
            righe.append("")
            righe.append("### Conversazione")
            for m in r.messages:
                righe.append("")
                righe.append(f"**{m['role']}**")
                righe.append("")
                righe.append(m["content"])
            if r.schema is not None:
                righe.append("")
                righe.append("### Schema della risposta")
                righe.append("")
                righe.append("```json")
                righe.append(json.dumps(r.schema, ensure_ascii=False))
                righe.append("```")
        else:
            righe.append("")
            ultimo = r.last_user_message
            righe.append(ultimo if len(ultimo) <= 400 else ultimo[:397] + "...")
        righe.append("")
    return "\n".join(righe).rstrip() + "\n"
