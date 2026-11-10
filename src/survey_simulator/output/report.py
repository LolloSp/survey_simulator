"""Report HTML del run: distribuzioni, segmenti, effetti di modalità, stabilità, segnali.

Grafici come SVG inline generati qui (niente librerie grafiche): barre
orizzontali per le distribuzioni, barre raggruppate per i confronti.
Ogni pagina è etichettata come SIMULATA.
"""

import html
from pathlib import Path
from typing import Any

import polars as pl
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from survey_simulator.output import analysis
from survey_simulator.output.wide import WideVariable
from survey_simulator.questionnaire.schema import Questionnaire, QuestionType

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "report.html.j2"
MODE_COLORS = {"cawi": "#2a6f97", "cati": "#e76f51", "capi": "#2a9d8f"}
PALETTE = ["#2a6f97", "#e76f51", "#2a9d8f", "#e9c46a", "#8d99ae", "#6a4c93", "#f4a261", "#264653"]

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    undefined=StrictUndefined,
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.0f}%"


def _num(x: float | None, digits: int = 2) -> str:
    return "-" if x is None else f"{x:.{digits}f}"


def bar_chart(shares: dict[str, float], *, color: str = "#2a6f97", width: int = 520) -> str:
    """Barre orizzontali: etichetta a sinistra, quota a destra."""
    if not shares:
        return ""
    righe = list(shares.items())
    h = 22
    altezza = h * len(righe) + 8
    massimo = max(v for _, v in righe) or 1.0
    parti = [
        f'<svg class="chart" viewBox="0 0 {width} {altezza}" width="{width}" height="{altezza}" '
        'role="img" aria-label="distribuzione">'
    ]
    for i, (etichetta, v) in enumerate(righe):
        y = 4 + i * h
        lung = int((width - 260) * v / massimo)
        testo = html.escape(etichetta if len(etichetta) <= 34 else etichetta[:31] + "...")
        parti.append(f'<text x="0" y="{y + 15}" font-size="12">{testo}</text>')
        parti.append(f'<rect x="210" y="{y + 3}" width="{lung}" height="{h - 8}" fill="{color}"/>')
        parti.append(f'<text x="{215 + lung}" y="{y + 15}" font-size="12">{_pct(v)}</text>')
    parti.append("</svg>")
    return "".join(parti)


def grouped_chart(groups: dict[str, float | None], *, width: int = 520, pct: bool) -> str:
    """Barre per gruppo (modalità o segmento) con colore per gruppo."""
    valori = {g: v for g, v in groups.items() if v is not None}
    if not valori:
        return ""
    h = 22
    altezza = h * len(valori) + 8
    massimo = max(abs(v) for v in valori.values()) or 1.0
    parti = [
        f'<svg class="chart" viewBox="0 0 {width} {altezza}" width="{width}" height="{altezza}" '
        'role="img" aria-label="confronto">'
    ]
    for i, (g, v) in enumerate(valori.items()):
        y = 4 + i * h
        lung = int((width - 260) * abs(v) / massimo)
        colore = MODE_COLORS.get(g, PALETTE[i % len(PALETTE)])
        parti.append(f'<text x="0" y="{y + 15}" font-size="12">{html.escape(g)}</text>')
        parti.append(f'<rect x="210" y="{y + 3}" width="{lung}" height="{h - 8}" fill="{colore}"/>')
        etichetta = _pct(v) if pct else _num(v)
        parti.append(f'<text x="{215 + lung}" y="{y + 15}" font-size="12">{etichetta}</text>')
    parti.append("</svg>")
    return "".join(parti)


def build_context(
    manifest: dict[str, Any],
    wide: pl.DataFrame,
    long: pl.DataFrame,
    variables: list[WideVariable],
    questionnaire: Questionnaire,
) -> dict[str, Any]:
    modes = sorted(wide["mode"].unique().to_list())
    segments = sorted(wide["segment"].unique().to_list()) if "segment" in wide.columns else []
    distribuzioni = []
    for var in variables:
        if var.kind in ("open", "status"):
            continue
        s = analysis.summarize(wide, var).get("tutti")
        if s is None:
            continue
        distribuzioni.append(
            {
                "name": var.name,
                "label": var.label,
                "kind": var.kind,
                "n": s.n,
                "missing": s.n_missing,
                "mean": _num(s.mean) if s.mean is not None else None,
                "chart": bar_chart(s.shares) if s.shares and var.kind != "multi_dummy" else "",
                "missing_shares": {k: _pct(v) for k, v in s.missing_shares.items()},
            }
        )
    effetti = []
    for riga in analysis.compare(wide, variables, "mode", reference="cawi"):
        pct = riga["kind"] in ("single", "multi_dummy")
        effetti.append(
            {
                **riga,
                "chart": grouped_chart({g: r["value"] for g, r in riga["groups"].items()}, pct=pct),
                "rows": [
                    {
                        "group": g,
                        "metric": r["metric"],
                        "value": _pct(r["value"]) if pct else _num(r["value"]),
                        "delta": (
                            "-"
                            if r["delta"] is None
                            else (f"{100 * r['delta']:+.0f} punti" if pct else f"{r['delta']:+.2f}")
                        ),
                        "missing": _pct(r["missing_rate"]),
                        "n": r["n"],
                    }
                    for g, r in riga["groups"].items()
                ],
            }
        )
    segmenti = []
    if len(segments) > 1:
        for riga in analysis.compare(wide, variables, "segment"):
            pct = riga["kind"] in ("single", "multi_dummy")
            segmenti.append(
                {
                    **riga,
                    "chart": grouped_chart(
                        {g: r["value"] for g, r in riga["groups"].items()}, pct=pct
                    ),
                    "rows": [
                        {
                            "group": g,
                            "metric": r["metric"],
                            "value": _pct(r["value"]) if pct else _num(r["value"]),
                            "n": r["n"],
                        }
                        for g, r in riga["groups"].items()
                    ],
                }
            )
    ensemble = []
    modelli = sorted(wide["model"].unique().to_list())
    if len(modelli) > 1:
        for riga in analysis.compare(wide, variables, "model"):
            pct = riga["kind"] in ("single", "multi_dummy")
            valori = [r["value"] for r in riga["groups"].values() if r["value"] is not None]
            divergenza = (max(valori) - min(valori)) if len(valori) > 1 else None
            ensemble.append(
                {
                    **riga,
                    "divergence": divergenza,
                    "divergence_text": (
                        "-"
                        if divergenza is None
                        else (f"{100 * divergenza:.0f} punti" if pct else f"{divergenza:.2f}")
                    ),
                    "rows": [
                        {
                            "group": g,
                            "metric": r["metric"],
                            "value": _pct(r["value"]) if pct else _num(r["value"]),
                            "n": r["n"],
                        }
                        for g, r in riga["groups"].items()
                    ],
                }
            )
        ensemble.sort(key=lambda e: -(e["divergence"] or 0.0))
    stati = analysis.status_by_mode(long)
    stabilita = analysis.replicate_stability(wide, variables)
    piatte = analysis.straightlining(wide, variables)
    open_ids = [q.id for q in questionnaire.questions if q.type == QuestionType.OPEN]
    stats = manifest.get("stats", {})
    costo = manifest.get("cost_eur")
    return {
        "manifest": manifest,
        "run_id": manifest.get("run_id", ""),
        "project": manifest.get("config", {}).get("project", {}).get("name", ""),
        "created_at": manifest.get("created_at", ""),
        "frozen": bool(manifest.get("frozen")),
        "status": manifest.get("status", ""),
        "models": [m.get("model") for m in manifest.get("models", [])],
        "design": manifest.get("plan", {}).get("design", ""),
        "replicates": manifest.get("plan", {}).get("replicates", ""),
        "interviews": manifest.get("interviews_done", 0),
        "skipped": manifest.get("interviews_skipped", 0),
        "personas": manifest.get("personas", 0),
        "modes": modes,
        "segments": segments,
        "cost_eur": _num(costo) if costo is not None else "-",
        "estimate_eur": _num(manifest.get("estimate", {}).get("cost_eur")),
        "stats": stats,
        "questionnaire": manifest.get("questionnaire", {}),
        "distribuzioni": distribuzioni,
        "effetti": effetti,
        "segmenti": segmenti,
        "stati": {m: {k: _pct(v) for k, v in d.items()} for m, d in stati.items()},
        "ensemble": ensemble,
        "models_count": len(modelli),
        "completamento": {m: _pct(v) for m, v in analysis.completion(long).items()},
        "stabilita": [{**s, "agreement_pct": _pct(s["agreement"])} for s in stabilita],
        "piatte": [
            {
                "question_id": p["question_id"],
                "by_mode": {m: f"{_pct(d['rate'])} (n={d['n']})" for m, d in p["by_mode"].items()},
            }
            for p in piatte
        ],
        "incongruenze_domanda": [
            {**r, "rate_pct": _pct(r["rate"])} for r in analysis.incongruence(long, "question_id")
        ],
        "incongruenze_segmento": [
            {**r, "rate_pct": _pct(r["rate"])} for r in analysis.incongruence(long, "segment")
        ],
        "interventi": {
            m: {
                "clarification": _pct(d["clarification_rate"]),
                "probe": _pct(d["probe_rate"]),
                "n": d["n"],
            }
            for m, d in analysis.probes_and_clarifications(long).items()
        },
        "aperte": {m: _num(c, 0) for m, c in analysis.open_answer_length(long, open_ids).items()},
        "nonverbal_enabled": bool(
            manifest.get("config", {}).get("engine", {}).get("nonverbal", {}).get("enabled", True)
        ),
    }


def render_report(context: dict[str, Any]) -> str:
    return _env.get_template(TEMPLATE_NAME).render(**context)


def write_report(context: dict[str, Any], path: Path) -> Path:
    path.write_text(render_report(context), encoding="utf-8")
    return path
