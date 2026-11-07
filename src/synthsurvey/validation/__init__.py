"""Validazione ex post: dati reali, allineamento, metriche, rapporto di confronto (M11)."""

from pathlib import Path

import polars as pl

from synthsurvey.output import WideVariable, build_wide, load_run
from synthsurvey.personas.build import personas_frame
from synthsurvey.validation.metrics import (
    ValidationResult,
    VariableComparison,
    compare_variables,
    distribution,
    js_divergence,
    mean_ci,
    mode_effect_direction,
    overall_correlation,
    pearson,
    share_ci,
    subgroup_coherence,
    summarize_result,
    total_variation,
)
from synthsurvey.validation.real import (
    Alignment,
    RealDataError,
    align,
    load_real,
    long_to_wide_real,
)
from synthsurvey.validation.report import to_json, to_markdown, write_validation


def validate_frames(
    simulated: pl.DataFrame, real: pl.DataFrame, variables: list[WideVariable]
) -> ValidationResult:
    """Confronto su dataset larghi già allineati per nome di variabile."""
    alignment = align(simulated, real, variables)
    sim = simulated.filter(pl.col("mode").is_in(alignment.modes)) if alignment.modes else simulated
    reale = real.filter(pl.col("mode").is_in(alignment.modes)) if alignment.modes else real
    comparisons = compare_variables(sim, reale, variables, alignment.variables)
    sottogruppi = [
        subgroup_coherence(sim, reale, variables, alignment.variables, by)
        for by in alignment.subgroup_columns
    ]
    effetti = mode_effect_direction(sim, reale, variables, alignment.variables, alignment.modes)
    result = ValidationResult(
        alignment=alignment,
        comparisons=comparisons,
        correlation=overall_correlation(comparisons),
        subgroups=sottogruppi,
        mode_effects=effetti,
    )
    result.summary = summarize_result(result)
    return result


def validate_run(
    run_dir: Path,
    real_path: Path,
    *,
    out_dir: Path | None = None,
    questionnaire_path: Path | None = None,
) -> tuple[ValidationResult, list[Path]]:
    """Carica il run e i dati reali, calcola le metriche e scrive il rapporto.

    Il rapporto va in `out_dir` (default `<run>/validation/`); un run congelato
    richiede una cartella diversa, perché la sua cartella non si tocca.
    """
    from synthsurvey.runner.manifest import FrozenError, is_frozen

    manifest, long, personas, questionnaire = load_run(run_dir, questionnaire_path)
    wide, variables = build_wide(long, personas_frame(personas), questionnaire)
    real = load_real(real_path, questionnaire)
    result = validate_frames(wide, real, variables)
    destinazione = out_dir or (run_dir / "validation")
    if is_frozen(run_dir) and destinazione.resolve().is_relative_to(run_dir.resolve()):
        raise FrozenError(f"run congelato: indicare --out fuori da {run_dir}")
    files = write_validation(
        result,
        destinazione,
        run_id=str(manifest.get("run_id", run_dir.name)),
        real_path=str(real_path),
    )
    return result, files


__all__ = [
    "Alignment",
    "RealDataError",
    "ValidationResult",
    "VariableComparison",
    "align",
    "compare_variables",
    "distribution",
    "js_divergence",
    "load_real",
    "long_to_wide_real",
    "mean_ci",
    "mode_effect_direction",
    "overall_correlation",
    "pearson",
    "share_ci",
    "subgroup_coherence",
    "summarize_result",
    "to_json",
    "to_markdown",
    "total_variation",
    "validate_frames",
    "validate_run",
    "write_validation",
]
