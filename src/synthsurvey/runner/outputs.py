"""Scrittura degli output di base di un run: persone, dataset lungo, trascrizioni, esiti.

I formati larghi, il file .sav, il codebook e il report arrivano con M10
(`synthsurvey.output`); qui si scrive ciò che serve a riprendere e
congelare un run.
"""

import json
from pathlib import Path
from typing import Any

import polars as pl

from synthsurvey.interview.records import AnswerRecord
from synthsurvey.interview.session import InterviewResult
from synthsurvey.personas.build import personas_frame
from synthsurvey.personas.schema import Persona

JSON_COLUMNS = ("option_order", "nonverbal_emitted", "nonverbal_observed")

LONG_SCHEMA: dict[str, type[pl.DataType]] = {
    "run_id": pl.String,
    "persona_id": pl.String,
    "segment": pl.String,
    "mode": pl.String,
    "replicate": pl.Int64,
    "model": pl.String,
    "question_id": pl.String,
    "item_id": pl.String,
    "status": pl.String,
    "answer_code": pl.String,
    "answer_text": pl.String,
    "option_order": pl.String,
    "clarification_requested": pl.Boolean,
    "item_nonresponse": pl.Boolean,
    "nonverbal_emitted": pl.String,
    "nonverbal_observed": pl.String,
    "incongruence": pl.Boolean,
    "probe": pl.Boolean,
    "tokens_in": pl.Int64,
    "tokens_out": pl.Int64,
    "latency_ms": pl.Int64,
    "page": pl.Int64,
    "position": pl.Int64,
}


def records_frame(records: list[AnswerRecord]) -> pl.DataFrame:
    """Dataset lungo: una riga per domanda e item; liste e dizionari come JSON."""
    righe = []
    for r in records:
        d = r.to_dict()
        for k in JSON_COLUMNS:
            d[k] = json.dumps(d[k], ensure_ascii=False) if d[k] is not None else None
        righe.append(d)
    if not righe:
        return pl.DataFrame(schema=LONG_SCHEMA)
    return pl.DataFrame(righe, schema=LONG_SCHEMA).sort(
        ["model", "persona_id", "mode", "replicate", "position"]
    )


def write_frame(frame: pl.DataFrame, path_stem: Path, formats: list[str]) -> list[Path]:
    scritti = []
    if "parquet" in formats:
        p = path_stem.with_suffix(".parquet")
        frame.write_parquet(p)
        scritti.append(p)
    if "csv" in formats:
        p = path_stem.with_suffix(".csv")
        frame.write_csv(p)
        scritti.append(p)
    return scritti


def write_personas(personas: list[Persona], run_dir: Path, formats: list[str]) -> list[Path]:
    scritti = write_frame(personas_frame(personas), run_dir / "personas", formats)
    (run_dir / "personas.json").write_text(
        json.dumps([p.model_dump(mode="json") for p in personas], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return [*scritti, run_dir / "personas.json"]


def transcript_markdown(result: InterviewResult) -> str:
    s = result.spec
    righe = [
        f"# {s.persona.persona_id} ({s.persona.segment}), {s.mode.value.upper()}, "
        f"replica {s.replicate}, modello {s.model}",
        "",
        "Trascrizione simulata: non è un'intervista reale.",
        "",
    ]
    for t in result.transcript:
        testa = f"**{t.speaker}**" + (f" [{t.question_id}]" if t.question_id else "")
        righe.append(testa)
        righe.append("")
        righe.append(t.text)
        if t.signals:
            attivi = [f"{k} {v}" for k, v in t.signals.items() if isinstance(v, int) and v]
            corpo = t.signals.get("body")
            if isinstance(corpo, dict):
                attivi.extend(f"{k}: {v}" for k, v in corpo.items() if v)
            if attivi:
                righe.append("")
                righe.append("*Segnali: " + "; ".join(attivi) + "*")
        righe.append("")
    return "\n".join(righe).rstrip() + "\n"


def write_transcripts(results: list[InterviewResult], run_dir: Path) -> int:
    cartella = run_dir / "transcripts"
    cartella.mkdir(parents=True, exist_ok=True)
    n = 0
    for res in results:
        if not res.transcript:
            continue
        s = res.spec
        nome = f"{s.persona.persona_id}_{s.mode.value}_r{s.replicate}_m{_slug(s.model)}.md"
        (cartella / nome).write_text(transcript_markdown(res), encoding="utf-8")
        n += 1
    return n


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text)


def interviews_summary(results: list[InterviewResult]) -> list[dict[str, Any]]:
    out = []
    for res in results:
        s = res.spec
        o = res.outcome
        out.append(
            {
                "persona_id": s.persona.persona_id,
                "segment": s.persona.segment,
                "mode": s.mode.value,
                "replicate": s.replicate,
                "model": s.model,
                "completed": o.completed,
                "abandoned_at": o.abandoned_at,
                "abandon_reason": o.abandon_reason,
                "calls": o.calls,
                "tokens_in": o.tokens_in,
                "tokens_out": o.tokens_out,
                "latency_ms": o.latency_ms,
                "refusals": o.refusals,
                "warnings": list(o.warnings),
            }
        )
    return out
