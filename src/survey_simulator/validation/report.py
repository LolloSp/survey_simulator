"""Rapporto di confronto fra simulato e reale, in Markdown e JSON."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from survey_simulator.validation.metrics import ValidationResult, summarize_result


def _f(x: float | None, digits: int = 3) -> str:
    return "-" if x is None else f"{x:.{digits}f}"


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def to_json(result: ValidationResult, *, run_id: str, real_path: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "real_path": real_path,
        "disclaimer": (
            "Confronto fra interviste SIMULATE e dati reali. Le modalità assenti nel reale "
            "restano stime non validate."
        ),
        "alignment": asdict(result.alignment),
        "summary": result.summary or summarize_result(result),
        "variables": [{**asdict(c), "diff": c.diff} for c in result.comparisons],
        "correlation": result.correlation,
        "subgroups": result.subgroups,
        "mode_effects": result.mode_effects,
    }


def to_markdown(result: ValidationResult, *, run_id: str, real_path: str) -> str:
    a = result.alignment
    s = result.summary or summarize_result(result)
    righe = [
        f"# Validazione del run `{run_id}` contro dati reali",
        "",
        "Confronto fra interviste **simulate** e dati reali. Le modalità assenti nel reale "
        "restano stime **non validate**.",
        "",
        "## Allineamento",
        "",
        f"- Dati reali: `{real_path}`, {a.n_real} righe (rispondente x modalità)",
        f"- Simulato: {a.n_simulated} righe (persona x modalità x replica x modello)",
        f"- Modalità confrontate: {', '.join(a.modes) if a.modes else 'nessuna'}"
        + (f"; solo nel reale: {', '.join(a.real_only_modes)}" if a.real_only_modes else "")
        + (
            f"; solo nel simulato (non validate): {', '.join(a.simulated_only_modes)}"
            if a.simulated_only_modes
            else ""
        ),
        f"- Variabili confrontabili: {len(a.variables)}"
        + (f"; assenti nel reale: {', '.join(a.missing_in_real)}" if a.missing_in_real else ""),
        f"- Sottogruppi disponibili in entrambi: {', '.join(a.subgroup_columns) or 'nessuno'}",
    ]
    righe.extend(f"- Avviso: {w}" for w in a.warnings)
    righe += [
        "",
        "## Sintesi",
        "",
        "| Metrica | Valore |",
        "|---|---|",
        f"| Variabili confrontate | {s['variables']} |",
        f"| Jensen-Shannon media (0 = identiche) | {_f(s['js_mean'])} |",
        f"| Variazione totale media | {_f(s['tv_mean'])} |",
        f"| Variabili con simulato dentro l'IC 95% del reale | {_pct(s['within_ci_share'])} |",
        f"| Correlazione quote simulate-reali (singole) | {_f(s['r_quote'])} |",
        f"| Correlazione medie simulate-reali (scale, griglie, multiple) | {_f(s['r_medie'])} |",
        f"| Accordo di segno degli effetti di modalità | {_pct(s['mode_sign_agreement'])} |",
        "",
        "## Per domanda",
        "",
        "| Variabile | Metrica | Reale | IC 95% | Simulato | Diff. | Dentro IC | JS | TV "
        "| n reale | n sim |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in result.comparisons:
        metrica = c.metric + (f" cod. {c.top_code}" if c.top_code is not None else "")
        fmt = _pct if c.metric == "quota" else _f
        dentro = "-" if c.within_ci is None else ("sì" if c.within_ci else "no")
        righe.append(
            f"| {c.name} | {metrica} | {fmt(c.real)} | {fmt(c.ci_low)}..{fmt(c.ci_high)} | "
            f"{fmt(c.simulated)} | {fmt(c.diff)} | {dentro} | {_f(c.js)} | {_f(c.tv)} | "
            f"{c.n_real} | {c.n_sim} |"
        )
    righe += ["", "## Sottogruppi", ""]
    if result.subgroups:
        righe += [
            "| Variabile di gruppo | Gruppi | Confronti | Accordo di segno | Correlazione |",
            "|---|---|---|---|---|",
        ]
        for g in result.subgroups:
            righe.append(
                f"| {g['by']} | {', '.join(map(str, g['groups']))} | {g['n']} | "
                f"{_pct(g['sign_agreement'])} | {_f(g['r'])} |"
            )
    else:
        righe.append("Nessun sottogruppo presente in entrambi i dataset.")
    righe += ["", "## Effetti di modalità", ""]
    me = result.mode_effects
    if me.get("n"):
        righe.append(
            f"Modalità osservate in entrambi: {', '.join(me['modes'])}. Confronti {me['n']}, "
            f"accordo di segno {_pct(me['sign_agreement'])}, correlazione {_f(me['r'])}."
        )
    else:
        righe.append(
            "Meno di due modalità in comune: nessuna verifica della direzione degli effetti."
        )
    righe += [
        "",
        "## Come leggere",
        "",
        "- JS e TV vicini a 0 e simulato dentro l'IC: la distribuzione simulata è compatibile "
        "con il reale al netto del rumore campionario.",
        "- Correlazioni alte con differenze sistematiche: il modello ordina bene le domande ma "
        "è spostato (bias di livello).",
        "- Accordo di segno basso sui sottogruppi: le differenze fra gruppi non sono riprodotte; "
        "da rivedere persone e priori prima di fidarsi delle letture per segmento.",
    ]
    return "\n".join(righe) + "\n"


def write_validation(
    result: ValidationResult, out_dir: Path, *, run_id: str, real_path: str
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / "validation.md"
    md.write_text(to_markdown(result, run_id=run_id, real_path=real_path), encoding="utf-8")
    js = out_dir / "validation.json"
    js.write_text(
        json.dumps(
            to_json(result, run_id=run_id, real_path=real_path), ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    return [md, js]
