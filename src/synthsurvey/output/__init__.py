"""Output di un run: dataset largo, .sav, codebook, report HTML, pagina delle interviste (M10).

`write_outputs(run_dir)` legge ciò che il runner ha scritto (manifest,
persone, dataset lungo) e produce il resto. Un run congelato non viene
toccato: gli output vanno in una cartella separata indicata dal chiamante.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from synthsurvey.output.analysis import (
    compare,
    completion,
    incongruence,
    replicate_stability,
    status_by_mode,
    straightlining,
    summarize,
)
from synthsurvey.output.codebook import build_codebook, write_codebook
from synthsurvey.output.interviews import (
    build_interviews_data,
    read_interviews,
    render_interviews_page,
    write_interviews_page,
)
from synthsurvey.output.report import build_context, render_report, write_report
from synthsurvey.output.sav import write_sav
from synthsurvey.output.wide import (
    MISSING,
    MISSING_LABELS,
    WideVariable,
    build_wide,
    wide_variables,
)
from synthsurvey.personas.schema import Persona
from synthsurvey.questionnaire.loader import parse_questionnaire
from synthsurvey.questionnaire.schema import Questionnaire
from synthsurvey.runner.manifest import FrozenError, is_frozen, read_manifest


class OutputError(Exception):
    """Cartella del run incompleta o questionario non ritrovato."""


@dataclass
class OutputResult:
    out_dir: Path
    files: list[Path] = field(default_factory=list)
    wide: pl.DataFrame | None = None
    variables: list[WideVariable] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


def load_run(
    run_dir: Path, questionnaire_path: Path | None = None
) -> tuple[dict[str, Any], pl.DataFrame, list[Persona], Questionnaire]:
    """Manifest, dataset lungo, persone e questionario di un run esistente."""
    manifest = read_manifest(run_dir)
    if manifest is None:
        raise OutputError(f"manifest assente in {run_dir}")
    lungo_path = run_dir / "responses_long.parquet"
    if not lungo_path.is_file():
        lungo_path = run_dir / "responses_long.csv"
    if not lungo_path.is_file():
        raise OutputError(f"dataset lungo assente in {run_dir}")
    long = (
        pl.read_parquet(lungo_path)
        if lungo_path.suffix == ".parquet"
        else pl.read_csv(lungo_path, infer_schema_length=None)
    )
    persone_path = run_dir / "personas.json"
    if not persone_path.is_file():
        raise OutputError(f"personas.json assente in {run_dir}")
    personas = [
        Persona.model_validate(p) for p in json.loads(persone_path.read_text(encoding="utf-8"))
    ]
    q_path = questionnaire_path or Path(manifest.get("questionnaire", {}).get("path", ""))
    if not q_path.is_file():
        raise OutputError(
            f"questionario non trovato: {q_path} (indicare --questionnaire se è stato spostato)"
        )
    import yaml

    raw = yaml.safe_load(q_path.read_text(encoding="utf-8"))
    return manifest, long, personas, parse_questionnaire(raw, q_path)


def write_outputs(
    run_dir: Path,
    *,
    out_dir: Path | None = None,
    questionnaire_path: Path | None = None,
    formats: list[str] | None = None,
) -> OutputResult:
    """Produce dataset largo (csv/parquet/sav), codebook e report nella cartella del run.

    Se il run è congelato, `out_dir` deve essere una cartella diversa.
    """
    manifest, long, personas, questionnaire = load_run(run_dir, questionnaire_path)
    destinazione = out_dir or run_dir
    if destinazione.resolve() == run_dir.resolve() and is_frozen(run_dir):
        raise FrozenError(
            f"run congelato: indicare --out per scrivere gli output altrove ({run_dir})"
        )
    destinazione.mkdir(parents=True, exist_ok=True)
    formati = formats or [
        str(f)
        for f in manifest.get("config", {})
        .get("output", {})
        .get("formats", ["parquet", "csv", "sav"])
    ]
    from synthsurvey.personas.build import personas_frame

    wide, variables = build_wide(long, personas_frame(personas), questionnaire)
    result = OutputResult(out_dir=destinazione, wide=wide, variables=variables)
    if "parquet" in formati:
        p = destinazione / "responses_wide.parquet"
        wide.write_parquet(p)
        result.files.append(p)
    if "csv" in formati:
        p = destinazione / "responses_wide.csv"
        wide.write_csv(p)
        result.files.append(p)
    if "sav" in formati:
        result.files.append(write_sav(wide, variables, destinazione / "responses_wide.sav"))
    codebook = build_codebook(
        str(manifest.get("run_id", run_dir.name)),
        questionnaire,
        variables,
        personas,
        manifest=manifest,
    )
    result.files.append(write_codebook(codebook, destinazione / "codebook.json"))
    context = build_context(manifest, wide, long, variables, questionnaire)
    result.context = context
    result.files.append(write_report(context, destinazione / "report.html"))
    pagina = build_interviews_data(
        manifest, long, personas, questionnaire, read_interviews(run_dir)
    )
    result.files.append(write_interviews_page(pagina, destinazione / "interviste.html"))
    return result


__all__ = [
    "MISSING",
    "MISSING_LABELS",
    "OutputError",
    "OutputResult",
    "WideVariable",
    "build_codebook",
    "build_context",
    "build_interviews_data",
    "build_wide",
    "compare",
    "completion",
    "incongruence",
    "load_run",
    "read_interviews",
    "render_interviews_page",
    "render_report",
    "replicate_stability",
    "status_by_mode",
    "straightlining",
    "summarize",
    "wide_variables",
    "write_codebook",
    "write_interviews_page",
    "write_outputs",
    "write_report",
    "write_sav",
]
