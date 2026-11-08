"""Esecuzione di un run completo: campione, persone, interviste, output, manifest.

Sequenza:

1. carica config e questionario, costruisce campione e persone (pilota:
   `run.pilot_size` persone);
2. costruisce il piano (disegno, repliche, modelli) e stima il costo: se
   supera `run.budget_max_eur` si ferma prima di qualsiasi chiamata;
3. esegue le interviste in parallelo entro la concorrenza dei pool; se la
   spesa reale supera il budget, le interviste non ancora iniziate vengono
   saltate e il run è marcato `budget_exceeded`;
4. scrive persone, dataset lungo, trascrizioni, esiti e manifest; con
   `run.frozen: true` congela subito.

Le risposte in cache (`engine.cache_dir`) rendono riavviabile un run
interrotto: le interviste già fatte non vengono pagate due volte.
"""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from synthsurvey import __version__
from synthsurvey.config.loader import LoadedConfig
from synthsurvey.config.schema import SynthSurveyConfig
from synthsurvey.interview.prompting import template_hashes
from synthsurvey.interview.session import InterviewResult, InterviewSpec, run_interview
from synthsurvey.llm.pool import LLMPool
from synthsurvey.llm.pricing import default_pricing
from synthsurvey.llm.registry import make_pool
from synthsurvey.personas.build import build_personas
from synthsurvey.personas.narrative import template_hash as persona_template_hash
from synthsurvey.personas.schema import Persona
from synthsurvey.population.istat.manifest import read_manifest as read_data_manifest
from synthsurvey.population.sample import SampleResult, build_sample
from synthsurvey.population.tables import IstatTables, load_tables
from synthsurvey.questionnaire.loader import load_questionnaire
from synthsurvey.questionnaire.modes import Mode, ModeQuestionnaire, adapt
from synthsurvey.questionnaire.schema import Questionnaire
from synthsurvey.runner.manifest import (
    FrozenError,
    assert_writable,
    freeze_run,
    is_frozen,
    now_iso,
    sha256_file,
    write_manifest,
)
from synthsurvey.runner.outputs import (
    interviews_summary,
    records_frame,
    write_frame,
    write_personas,
    write_transcripts,
)
from synthsurvey.runner.plan import (
    BudgetError,
    CostEstimate,
    InterviewPlan,
    build_plan,
    estimate_cost,
)

Progress = Callable[[int, int, float], None]  # fatte, totali, spesa in euro


@dataclass
class RunResult:
    run_id: str
    run_dir: Path
    manifest: dict[str, Any]
    estimate: CostEstimate
    results: list[InterviewResult] = field(default_factory=list)
    skipped: int = 0
    cost_eur: float = 0.0

    @property
    def budget_exceeded(self) -> bool:
        return self.skipped > 0


def default_run_id(config: SynthSurveyConfig, *, pilot: bool) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffisso = "-pilota" if pilot else ""
    return f"{config.project.name}-{stamp}{suffisso}"


def prepare(
    loaded: LoadedConfig,
    *,
    data_dir: Path,
    pilot: bool,
    tables: IstatTables | None = None,
) -> tuple[list[Persona], Questionnaire, dict[Mode, ModeQuestionnaire], IstatTables, SampleResult]:
    """Persone e questionario pronti per il piano (nessuna chiamata LLM)."""
    cfg = loaded.config
    processed = data_dir / "processed"
    tables = tables if tables is not None else load_tables(processed)
    n_total = cfg.run.pilot_size if pilot else None
    sample = build_sample(cfg, processed, n_total=n_total, tables=tables)
    personas = build_personas(sample, cfg, tables, processed_dir=processed).personas
    questionnaire = load_questionnaire(cfg.questionnaire.path, cfg).questionnaire
    mqs = {Mode(m.value): adapt(questionnaire, Mode(m.value)) for m in cfg.modes.enabled}
    return personas, questionnaire, mqs, tables, sample


def write_private_map(run_dir: Path, personas: list[Persona], sample: Any) -> Path | None:
    """Anagrafiche: scrive `private/contacts_map.csv` (persona -> record), fuori dagli output."""
    mappa = getattr(sample, "private_map", None)
    if mappa is None or mappa.height == 0:
        return None
    import polars as pl

    persone = pl.DataFrame(
        {"unit_id": [p.unit_id for p in personas], "persona_id": [p.persona_id for p in personas]}
    )
    cartella = run_dir / "private"
    cartella.mkdir(parents=True, exist_ok=True)
    path = cartella / "contacts_map.csv"
    mappa.join(persone, on="unit_id", how="left").select(
        ["persona_id", "unit_id", "record_id", "row"]
    ).write_csv(path)
    (cartella / "LEGGIMI.txt").write_text(
        "Corrispondenza fra persone sintetiche e record dell'anagrafica del committente.\n"
        "Contiene identificativi dei clienti: non condividere questa cartella.\n",
        encoding="utf-8",
    )
    return path


def _manifest_base(
    loaded: LoadedConfig,
    run_id: str,
    *,
    pilot: bool,
    data_dir: Path,
    personas: list[Persona],
    plan: list[InterviewPlan],
    estimate: CostEstimate,
) -> dict[str, Any]:
    cfg = loaded.config
    dati = read_data_manifest(data_dir / "processed")
    tavole = {}
    if dati is not None:
        for nome, voce in dati.tables.items():
            tavole[nome] = {
                "sha256": voce.sha256,
                "fetched_at": getattr(voce, "fetched_at", None),
            }
    return {
        "run_id": run_id,
        "synthsurvey_version": __version__,
        "created_at": now_iso(),
        "pilot": pilot,
        "frozen": False,
        "config_path": str(loaded.path),
        "config_sha256": sha256_file(loaded.path) if loaded.path.is_file() else None,
        "config": cfg.model_dump(mode="json"),
        "questionnaire": {
            "path": str(cfg.questionnaire.path),
            "sha256": sha256_file(cfg.questionnaire.path),
        },
        "data_tables": tavole,
        "prompts": {**template_hashes(), "persona_it.j2": persona_template_hash()},
        "priors_path": str(cfg.personas.priors_path) if cfg.personas.priors_path else None,
        "models": [m.model_dump() for m in cfg.engine.models],
        "seed": cfg.project.seed,
        "personas": len(personas),
        "plan": {
            "interviews": len(plan),
            "design": cfg.modes.design.value,
            "modes": [m.value for m in cfg.modes.enabled],
            "replicates": cfg.engine.replicates,
        },
        "estimate": {
            "calls": estimate.calls,
            "input_tokens": estimate.input_tokens,
            "output_tokens": estimate.output_tokens,
            "cost_usd": round(estimate.cost_usd, 4),
            "cost_eur": round(estimate.cost_eur, 4),
            "budget_eur": estimate.budget_eur,
            "by_model": estimate.by_model,
        },
    }


async def _execute(
    plan: list[InterviewPlan],
    personas: list[Persona],
    questionnaire: Questionnaire,
    mqs: dict[Mode, ModeQuestionnaire],
    pools: list[LLMPool],
    cfg: SynthSurveyConfig,
    run_id: str,
    progress: Progress | None,
) -> tuple[list[InterviewResult], int]:
    budget = cfg.run.budget_max_eur
    stato = {"fatte": 0, "saltate": 0}
    lock = asyncio.Lock()

    def spesa_eur() -> float:
        return sum(p.stats.cost_usd for p in pools) * cfg.engine.eur_per_usd

    async def una(item: InterviewPlan) -> InterviewResult | None:
        async with lock:
            if spesa_eur() > budget:
                stato["saltate"] += 1
                return None
        pool = pools[item.model_index]
        spec = InterviewSpec(
            run_id=run_id,
            persona=personas[item.persona_index],
            persona_index=item.persona_index,
            mode=item.mode,
            replicate=item.replicate,
            model=pool.client.model,
            seed=cfg.project.seed,
        )
        res = await run_interview(spec, questionnaire, mqs[item.mode], pool, cfg)
        async with lock:
            stato["fatte"] += 1
            if progress is not None:
                progress(stato["fatte"], len(plan), spesa_eur())
        return res

    esiti = await asyncio.gather(*(una(item) for item in plan))
    return [r for r in esiti if r is not None], stato["saltate"]


def execute_run(
    loaded: LoadedConfig,
    *,
    data_dir: Path = Path("data"),
    pilot: bool = False,
    run_id: str | None = None,
    use_cache: bool = True,
    pools: list[LLMPool] | None = None,
    tables: IstatTables | None = None,
    progress: Progress | None = None,
    estimate_only: bool = False,
) -> RunResult:
    """Esegue il run e scrive la cartella `<output.dir>/<run_id>`.

    `pools` permette di iniettare client (nei test, il client finto). Con
    `estimate_only` si ferma dopo la stima, senza chiamate né scritture.
    """
    cfg = loaded.config
    run_id = run_id or default_run_id(cfg, pilot=pilot)
    run_dir = cfg.output.dir / run_id
    if is_frozen(run_dir):
        raise FrozenError(f"run già congelato: {run_dir}")
    personas, questionnaire, mqs, _tables, sample = prepare(
        loaded, data_dir=data_dir, pilot=pilot, tables=tables
    )
    plan = build_plan(cfg, personas)
    pricing = default_pricing(cfg.engine.eur_per_usd)
    estimate = estimate_cost(cfg, plan, personas, mqs, pricing)
    manifest = _manifest_base(
        loaded,
        run_id,
        pilot=pilot,
        data_dir=data_dir,
        personas=personas,
        plan=plan,
        estimate=estimate,
    )
    result = RunResult(run_id=run_id, run_dir=run_dir, manifest=manifest, estimate=estimate)
    if not estimate.within_budget:
        raise BudgetError(
            f"stima {estimate.cost_eur:.2f} EUR oltre il budget {estimate.budget_eur:.2f} EUR: "
            "ridurre campione, repliche o modalità, oppure alzare run.budget_max_eur"
        )
    if estimate_only:
        return result
    if pools is None:
        pools = [
            make_pool(spec, cfg, pricing=pricing, use_cache=use_cache) for spec in cfg.engine.models
        ]
    assert_writable(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest["status"] = "running"
    manifest["started_at"] = now_iso()
    write_manifest(run_dir, manifest)

    results, skipped = asyncio.run(
        _execute(plan, personas, questionnaire, mqs, pools, cfg, run_id, progress)
    )
    result.results = results
    result.skipped = skipped
    result.cost_eur = sum(p.stats.cost_usd for p in pools) * cfg.engine.eur_per_usd

    formati = [f.value for f in cfg.output.formats]
    write_personas(personas, run_dir, formati)
    write_private_map(run_dir, personas, sample)
    records = [r for res in results for r in res.records]
    write_frame(records_frame(records), run_dir / "responses_long", formati)
    n_trascrizioni = write_transcripts(results, run_dir)
    (run_dir / "interviews.json").write_text(
        json.dumps(interviews_summary(results), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    stats = {f"{p.client.provider}/{p.client.model}": p.stats.as_dict() for p in pools}
    manifest["status"] = "budget_exceeded" if skipped else "completed"
    manifest["finished_at"] = now_iso()
    manifest["interviews_done"] = len(results)
    manifest["interviews_skipped"] = skipped
    manifest["records"] = len(records)
    manifest["transcripts"] = n_trascrizioni
    manifest["stats"] = stats
    manifest["cost_eur"] = round(result.cost_eur, 4)
    write_manifest(run_dir, manifest)
    # Dataset largo, .sav, codebook e report (M10): import locale per evitare cicli.
    from synthsurvey.output import write_outputs

    write_outputs(run_dir, questionnaire_path=cfg.questionnaire.path, formats=formati)
    if cfg.run.frozen:
        manifest = freeze_run(run_dir)
    result.manifest = manifest
    return result
