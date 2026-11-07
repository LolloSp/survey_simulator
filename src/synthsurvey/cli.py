"""Interfaccia a riga di comando di synthsurvey.

I comandi sono registrati qui ma implementati nelle rispettive milestone
(vedi docs/SPEC.md, sezione Roadmap). Finché non sono implementati
stampano un avviso ed escono con codice 1.
"""

from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from synthsurvey import __version__
from synthsurvey.config import ConfigError, estimate_interviews, load_config, segment_sizes

app = typer.Typer(
    name="synthsurvey",
    help="Simulatore di indagini su popolazione sintetica italiana.",
    no_args_is_help=True,
    add_completion=False,
)
config_app = typer.Typer(help="Validazione del file di configurazione.", no_args_is_help=True)
data_app = typer.Typer(help="Gestione delle tabelle sorgente ISTAT.", no_args_is_help=True)
sample_app = typer.Typer(help="Popolazione sintetica e campione.", no_args_is_help=True)
personas_app = typer.Typer(
    help="Persone: attributi, stile di risposta, narrativa.", no_args_is_help=True
)
llm_app = typer.Typer(
    help="Livello LLM: prezzi e verifica delle credenziali.", no_args_is_help=True
)
questionnaire_app = typer.Typer(
    help="Questionario: validazione e versioni per modalità.", no_args_is_help=True
)
app.add_typer(config_app, name="config")
app.add_typer(data_app, name="data")
app.add_typer(sample_app, name="sample")
app.add_typer(personas_app, name="personas")
interview_app = typer.Typer(help="Interviste simulate: pilota per modalità.", no_args_is_help=True)
app.add_typer(questionnaire_app, name="questionnaire")
app.add_typer(llm_app, name="llm")
app.add_typer(interview_app, name="interview")

ConfigOption = Annotated[
    Path,
    typer.Option("--config", "-c", help="File YAML di configurazione del progetto."),
]


def _non_implementato(comando: str, milestone: str) -> None:
    typer.secho(
        f"Comando '{comando}' non ancora implementato (previsto in {milestone}).",
        fg=typer.colors.YELLOW,
        err=True,
    )
    raise typer.Exit(code=1)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"synthsurvey {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Mostra la versione ed esce.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Simulatore di indagini su popolazione sintetica italiana."""
    # Chiavi API solo da ambiente: .env (non versionato) viene caricato qui.
    load_dotenv()


@config_app.command("validate")
def config_validate(
    file: Annotated[Path, typer.Argument(help="File YAML di configurazione da validare.")],
) -> None:
    """Valida un file di configurazione: elenca errori e avvisi, stima il volume del run."""
    try:
        loaded = load_config(file)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    cfg = loaded.config
    typer.secho(f"Configurazione valida: {loaded.path}", fg=typer.colors.GREEN)
    typer.echo(f"Progetto: {cfg.project.name} (seed {cfg.project.seed})")
    sizes = segment_sizes(cfg)
    typer.echo("Segmenti: " + ", ".join(f"{n}={k}" for n, k in sizes.items()))
    stima = estimate_interviews(cfg)
    typer.echo(
        f"Interviste previste: {stima.interviews} "
        f"({stima.personas} persone x {stima.modes_per_persona} modalità "
        f"x {stima.replicates} repliche x {stima.models} modelli)"
    )
    from synthsurvey.questionnaire import QuestionnaireError, load_questionnaire

    try:
        lq = load_questionnaire(cfg.questionnaire.path, cfg)
        typer.echo(
            f"Questionario: {lq.questionnaire.id} v{lq.questionnaire.version}, "
            f"{len(lq.questionnaire.questions)} domande, valido"
        )
        loaded_warnings = list(loaded.warnings)
        extra = [f"questionnaire: {w}" for w in lq.warnings]
    except QuestionnaireError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    if loaded_warnings or extra:
        n_avvisi = len(loaded_warnings) + len(extra)
        typer.secho(f"Avvisi ({n_avvisi}):", fg=typer.colors.YELLOW)
        for w in loaded_warnings:
            typer.secho(f"  - {w.location}: {w.message}", fg=typer.colors.YELLOW)
        for e in extra:
            typer.secho(f"  - {e}", fg=typer.colors.YELLOW)


DataDirOption = Annotated[
    Path,
    typer.Option("--data-dir", help="Cartella dati con le sottocartelle raw/ e processed/."),
]


@data_app.command("fetch")
def data_fetch(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Config di progetto: limita le tavole alle sorgenti usate dai segmenti.",
        ),
    ] = None,
    table: Annotated[
        list[str] | None,
        typer.Option("--table", "-t", help="Nome di una tavola da aggiornare (ripetibile)."),
    ] = None,
    offline: Annotated[
        bool, typer.Option("--offline", help="Non usa la rete: rigenera solo dalla cache grezza.")
    ] = False,
    data_dir: DataDirOption = Path("data"),
) -> None:
    """Scarica le tavole ISTAT via SDMX, le normalizza e aggiorna il manifest delle fonti."""
    from synthsurvey.population.istat import (
        TABLES,
        SdmxClient,
        SdmxError,
        fetch_tables,
        tables_for_sources,
    )
    from synthsurvey.population.istat.normalize import NormalizeError

    if table:
        ignote = [t for t in table if t not in TABLES]
        if ignote:
            typer.secho(
                f"Tavole sconosciute: {', '.join(ignote)}. Disponibili: {', '.join(TABLES)}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        specs = [TABLES[t] for t in table]
    elif config is not None:
        try:
            loaded = load_config(config)
        except ConfigError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from None
        sorgenti = [s.source for s in loaded.config.sample.segments.values()]
        specs = tables_for_sources(sorgenti)
    else:
        specs = list(TABLES.values())

    client = SdmxClient(data_dir / "raw", offline=offline)
    processed = data_dir / "processed"
    typer.echo(f"Tavole da aggiornare: {', '.join(s.name for s in specs)}")
    try:
        for spec in specs:
            typer.echo(f"- {spec.name}: {spec.description} [{spec.period}]")
            result = fetch_tables(client, [spec], processed)
            entry = result.manifest.tables[spec.name]
            cache = "cache" if all(r.from_cache for r in entry.raw) else "rete"
            typer.echo(f"  {entry.rows} righe, {entry.file}, sorgente da {cache}")
    except (SdmxError, NormalizeError) as exc:
        typer.secho(f"Errore: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    typer.secho(f"Manifest aggiornato: {processed / 'manifest.json'}", fg=typer.colors.GREEN)


@data_app.command("status")
def data_status(data_dir: DataDirOption = Path("data")) -> None:
    """Elenca le tavole nel manifest e verifica gli hash dei file."""
    from synthsurvey.population.istat import read_manifest, verify_manifest

    processed = data_dir / "processed"
    manifest = read_manifest(processed)
    if manifest is None:
        typer.secho(f"Nessun manifest in {processed}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Manifest generato il {manifest.generated_at} da {manifest.sdmx_base_url}")
    typer.echo(f"Licenza: {manifest.license.get('name', '?')}")
    for name, entry in manifest.tables.items():
        typer.echo(f"- {name} [{entry.period}] {entry.rows} righe, {entry.file}")
        typer.echo(f"  {entry.source_name}")
    problemi = verify_manifest(processed, data_dir / "raw")
    if problemi:
        typer.secho("Problemi:", fg=typer.colors.RED, err=True)
        for p in problemi:
            typer.secho(f"  - {p}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho("Hash verificati: tutto coerente.", fg=typer.colors.GREEN)


@sample_app.command("preview")
def sample_preview(
    config: ConfigOption = Path("config.yaml"),
    pilot: Annotated[
        bool, typer.Option("--pilot", help="Usa run.pilot_size invece di sample.total.")
    ] = False,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Cartella in cui salvare sample.csv e sample_diagnostics.json."),
    ] = None,
    data_dir: DataDirOption = Path("data"),
) -> None:
    """Costruisce il campione e mostra per segmento quote, celle piccole, conteggi e pesi."""
    import json

    from synthsurvey.population.quotas import QuotaError
    from synthsurvey.population.sample import build_sample
    from synthsurvey.population.tables import TablesError

    try:
        loaded = load_config(config)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    cfg = loaded.config
    n_total = cfg.run.pilot_size if pilot else None
    try:
        result = build_sample(cfg, data_dir / "processed", n_total=n_total)
    except (TablesError, QuotaError) as exc:
        typer.secho(f"Errore: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    typer.secho(
        f"Campione per {result.project} (seed {result.seed}): {result.units.height} unità"
        + (" [pilota]" if pilot else ""),
        fg=typer.colors.GREEN,
    )
    typer.echo(
        f"IPF individui: {result.ipf_iterations} iterazioni, residuo {result.ipf_max_rel_error:.1e}"
    )
    diagnostics: dict[str, object] = {
        "project": result.project,
        "seed": result.seed,
        "pilot": pilot,
        "units": result.units.height,
        "segments": {},
        "warnings": result.warnings,
    }
    for name, seg in result.segments.items():
        typer.echo(
            f"\n== {name} ({seg.source}): n={seg.n}, "
            f"popolazione filtrata {seg.population_total:,.0f}"
        )
        seg_diag: dict[str, object] = {
            "n": seg.n,
            "population_total": seg.population_total,
            "swaps": seg.draw.swaps,
            "max_deviation": seg.draw.max_deviation,
            "weights": seg.weights.summary(),
            "quotas": {},
        }
        for t in seg.targets:
            etichetta = " (sovracampionata)" if t.oversampled else ""
            typer.echo(f"  {t.variable}{etichetta}:")
            for c in t.targets:
                typer.echo(
                    f"    {c:<20} popolazione {t.population_shares[c]:6.1%}  "
                    f"target {t.targets[c]:4d}  ottenuto {seg.draw.achieved[t.variable][c]:4d}"
                )
            seg_diag["quotas"][t.variable] = {  # type: ignore[index]
                "population_shares": t.population_shares,
                "targets": t.targets,
                "achieved": seg.draw.achieved[t.variable],
                "oversampled": t.oversampled,
            }
        s = seg.weights.summary()
        typer.echo(
            f"  pesi: min {s['min']:.2f}, mediana {s['median']:.2f}, max {s['max']:.2f}, "
            f"deff {s['deff']:.2f}"
        )
        diagnostics["segments"][name] = seg_diag  # type: ignore[index]
    if result.warnings:
        typer.secho(f"\nAvvisi ({len(result.warnings)}):", fg=typer.colors.YELLOW)
        for w in result.warnings:
            typer.secho(f"  - {w}", fg=typer.colors.YELLOW)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        result.units.write_csv(out / "sample.csv")
        (out / "sample_diagnostics.json").write_text(
            json.dumps(diagnostics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        typer.echo(f"\nSalvati {out / 'sample.csv'} e {out / 'sample_diagnostics.json'}")


@personas_app.command("preview")
def personas_preview(
    config: ConfigOption = Path("config.yaml"),
    pilot: Annotated[
        bool, typer.Option("--pilot", help="Usa run.pilot_size invece di sample.total.")
    ] = False,
    n: Annotated[
        int | None,
        typer.Option("--n", help="Numero di persone da generare (sostituisce il totale)."),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Cartella per personas.json, personas.csv e personas.md."),
    ] = None,
    data_dir: DataDirOption = Path("data"),
) -> None:
    """Costruisce campione e persone; mostra distribuzioni, provenienze e avvisi."""
    import json
    from collections import Counter

    from synthsurvey.personas import build_personas, personas_markdown
    from synthsurvey.population.quotas import QuotaError
    from synthsurvey.population.sample import build_sample
    from synthsurvey.population.tables import TablesError, load_tables

    try:
        loaded = load_config(config)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    cfg = loaded.config
    n_total = n if n is not None else (cfg.run.pilot_size if pilot else None)
    processed = data_dir / "processed"
    try:
        tables = load_tables(processed)
        sample = build_sample(cfg, processed, n_total=n_total, tables=tables)
        result = build_personas(sample, cfg, tables, processed_dir=processed)
    except (TablesError, QuotaError) as exc:
        typer.secho(f"Errore: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    typer.secho(
        f"Persone per {cfg.project.name} (seed {cfg.project.seed}): {len(result.personas)}",
        fg=typer.colors.GREEN,
    )
    frame = result.frame
    for segment in sorted(frame["segment"].unique().to_list()):
        sub = frame.filter(frame["segment"] == segment)
        typer.echo(f"\n== {segment}: {sub.height} persone")
        for col in ("trust", "internet", "political_info", "economic_judgement", "income_quintile"):
            conte = Counter(sub[col].to_list())
            dettagli = ", ".join(
                f"{k}={v}" for k, v in sorted(conte.items(), key=lambda kv: str(kv[0]))
            )
            typer.echo(f"  {col}: {dettagli}")
        if sub["respondent_role"].drop_nulls().len() > 0:
            conte = Counter(sub["respondent_role"].drop_nulls().to_list())
            typer.echo(
                "  respondent_role: " + ", ".join(f"{k}={v}" for k, v in sorted(conte.items()))
            )
    typer.echo(
        "\nProvenienze: "
        + ", ".join(f"{k}={v}" for k, v in sorted(result.diagnostics["provenienze"].items()))
    )
    if result.diagnostics["riestrazioni"]:
        typer.echo(
            "Riestrazioni per coerenza: "
            + ", ".join(f"{k} ({v})" for k, v in result.diagnostics["riestrazioni"].items())
        )
    if result.warnings:
        typer.secho(f"\nAvvisi ({len(result.warnings)}):", fg=typer.colors.YELLOW)
        for w in result.warnings:
            typer.secho(f"  - {w}", fg=typer.colors.YELLOW)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "personas.json").write_text(
            json.dumps(
                [p.model_dump(mode="json") for p in result.personas], indent=2, ensure_ascii=False
            )
            + "\n",
            encoding="utf-8",
        )
        frame.write_csv(out / "personas.csv")
        (out / "personas.md").write_text(personas_markdown(result.personas), encoding="utf-8")
        typer.echo(f"\nSalvati personas.json, personas.csv e personas.md in {out}")


@questionnaire_app.command("validate")
def questionnaire_validate(
    file: Annotated[Path, typer.Argument(help="File YAML del questionario.")],
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config di progetto per controllare i segmenti."),
    ] = None,
) -> None:
    """Valida il questionario: schema, routing e, con la config, i segmenti citati."""
    from synthsurvey.questionnaire import Mode, QuestionnaireError, adapt, load_questionnaire

    cfg = None
    if config is not None:
        try:
            cfg = load_config(config).config
        except ConfigError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from None
    try:
        loaded = load_questionnaire(file, cfg)
    except QuestionnaireError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    q = loaded.questionnaire
    typer.secho(f"Questionario valido: {loaded.path} ({q.id} v{q.version})", fg=typer.colors.GREEN)
    typer.echo(
        f"Sezioni: {len(q.sections)}, domande: {len(q.questions)}, hash {loaded.sha256[:12]}"
    )
    for mode in Mode:
        typer.echo(f"  {mode.value}: {len(adapt(q, mode).questions)} domande presentate")
    if loaded.warnings:
        typer.secho(f"Avvisi ({len(loaded.warnings)}):", fg=typer.colors.YELLOW)
        for w in loaded.warnings:
            typer.secho(f"  - {w}", fg=typer.colors.YELLOW)


@questionnaire_app.command("export")
def questionnaire_export(
    file: Annotated[Path, typer.Argument(help="File YAML del questionario.")],
    out: Annotated[Path, typer.Option("--out", help="Cartella di destinazione.")],
    mode: Annotated[str, typer.Option("--mode", help="cawi, cati, capi oppure all.")] = "all",
) -> None:
    """Esporta le versioni per modalità in YAML e Markdown per la revisione."""
    from synthsurvey.questionnaire import (
        Mode,
        QuestionnaireError,
        adapt,
        export,
        load_questionnaire,
    )

    try:
        loaded = load_questionnaire(file)
    except QuestionnaireError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    modalita = list(Mode) if mode == "all" else [Mode(mode)]
    for m in modalita:
        hashes = export(adapt(loaded.questionnaire, m), out)
        for nome, h in hashes.items():
            typer.echo(f"{nome}  {h[:12]}")
    typer.secho(f"Esportato in {out}", fg=typer.colors.GREEN)


@questionnaire_app.command("import")
def questionnaire_import(
    file: Annotated[
        Path, typer.Argument(help="Questionario grezzo: .docx, .pdf, .xlsx, .txt, .md.")
    ],
    config: ConfigOption = Path("config.yaml"),
    out: Annotated[
        Path | None,
        typer.Option("--out", help="YAML di destinazione (default: accanto al sorgente)."),
    ] = None,
    report_path: Annotated[
        Path | None,
        typer.Option("--report", help="Rapporto Markdown (default: <out>.import.md)."),
    ] = None,
    rounds: Annotated[
        int, typer.Option("--rounds", min=0, help="Giri di correzione dopo il primo.")
    ] = 2,
    effort: Annotated[
        str, typer.Option("--effort", help="Profondità di ragionamento: low, medium, high.")
    ] = "high",
    max_tokens: Annotated[
        int, typer.Option("--max-tokens", min=1024, help="Token massimi per risposta.")
    ] = 16_000,
    model_index: Annotated[
        int, typer.Option("--model-index", help="Quale modello di engine.models usare (da 0).")
    ] = 0,
    use_cache: Annotated[
        bool, typer.Option("--cache/--no-cache", help="Riusa le risposte in cache.")
    ] = True,
) -> None:
    """Trascrive un questionario grezzo in YAML con un agente LLM e scrive il rapporto.

    Esce con 0 se lo YAML è valido, con 2 se è stato scritto ma resta da correggere.
    La revisione umana è comunque obbligatoria.
    """
    import asyncio
    from typing import cast

    from synthsurvey.llm import LLMError, make_pool
    from synthsurvey.llm.client import Effort
    from synthsurvey.questionnaire import (
        ExtractionError,
        extract_text,
        import_questionnaire,
        render_report,
        to_source_yaml,
    )

    if effort not in ("low", "medium", "high"):
        typer.secho("--effort deve essere low, medium o high", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    try:
        cfg = load_config(config).config
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    if model_index >= len(cfg.engine.models):
        typer.secho("model-index fuori dalla lista engine.models", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    try:
        doc = extract_text(file)
    except ExtractionError as exc:
        typer.secho(f"Errore di estrazione: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Testo estratto da {doc.path.name}: {doc.chars} caratteri")
    for w in doc.warnings:
        typer.secho(f"Avviso: {w}", fg=typer.colors.YELLOW)
    spec = cfg.engine.models[model_index]
    try:
        pool = make_pool(spec, cfg, use_cache=use_cache)
        result = asyncio.run(
            import_questionnaire(
                doc,
                pool,
                config=cfg,
                effort=cast(Effort, effort),
                max_tokens=max_tokens,
                max_rounds=rounds,
            )
        )
    except LLMError as exc:
        typer.secho(f"Errore LLM: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    yaml_path = out if out is not None else file.with_suffix(".yaml")
    if not result.valid and result.raw is not None:
        yaml_path = yaml_path.with_name(yaml_path.stem + ".draft.yaml")
    md_path = report_path if report_path is not None else yaml_path.with_suffix(".import.md")
    if result.raw is not None:
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(to_source_yaml(result.raw, result), encoding="utf-8")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(
        render_report(result, yaml_path=yaml_path if result.raw is not None else None),
        encoding="utf-8",
    )
    s = result.stats.as_dict()
    typer.echo(
        f"Giri {len(result.rounds)}, chiamate {s['calls']}, cache {s['cache_hits']}, "
        f"costo {s['cost_usd']:.4f} USD"
    )
    typer.echo(f"Rapporto: {md_path}")
    if result.valid:
        q = result.questionnaire
        assert q is not None
        typer.secho(
            f"YAML valido: {yaml_path} ({q.id}, {len(q.sections)} sezioni, "
            f"{len(q.questions)} domande). Da revisionare prima dell'uso.",
            fg=typer.colors.GREEN,
        )
        return
    if result.raw is not None:
        typer.secho(
            f"Bozza NON valida salvata in {yaml_path}: {len(result.errors)} errori da "
            "correggere a mano (vedi rapporto).",
            fg=typer.colors.YELLOW,
            err=True,
        )
    else:
        typer.secho(
            "Nessuna bozza prodotta: " + "; ".join(result.errors), fg=typer.colors.RED, err=True
        )
    raise typer.Exit(code=2)


@llm_app.command("prices")
def llm_prices() -> None:
    """Mostra la tabella prezzi dei modelli (dollari per milione di token)."""
    from synthsurvey.llm import load_prices

    table = load_prices()
    typer.echo(
        f"Prezzi aggiornati al {table.updated} ({table.currency}/MTok), fonte {table.source}"
    )
    typer.echo(f"{'modello':22} {'input':>8} {'output':>8} {'cache w':>8} {'cache r':>8}")
    for name, p in table.models.items():
        typer.echo(
            f"{name:22} {p.input:8.2f} {p.output:8.2f} {p.cache_write:8.3f} {p.cache_read:8.3f}"
        )


@llm_app.command("ping")
def llm_ping(
    config: ConfigOption = Path("config.yaml"),
    model_index: Annotated[
        int, typer.Option("--model-index", help="Quale modello di engine.models usare (da 0).")
    ] = 0,
) -> None:
    """Una sola chiamata reale al provider per verificare credenziali, modello e costo."""
    import asyncio

    from synthsurvey.llm import LLMError, LLMRequest, Message, make_pool

    try:
        cfg = load_config(config).config
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    if model_index >= len(cfg.engine.models):
        typer.secho("model-index fuori dalla lista engine.models", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    spec = cfg.engine.models[model_index]
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "modello": {"type": "string"}},
        "required": ["ok", "modello"],
        "additionalProperties": False,
    }
    request = LLMRequest(
        system="Sei un assistente di prova. Rispondi solo nel formato richiesto.",
        messages=(Message("user", "Conferma che funzioni e indica il tuo nome di modello."),),
        schema=schema,
        max_tokens=64,
        effort=cfg.engine.effort,
        variant="ping",
    )
    try:
        pool = make_pool(spec, cfg, use_cache=False)
        response = asyncio.run(pool.complete(request))
    except LLMError as exc:
        typer.secho(f"Errore: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    stats = pool.stats.as_dict()
    typer.secho(f"Provider {spec.provider}, modello {response.model}: ok", fg=typer.colors.GREEN)
    typer.echo(f"Risposta: {response.text}")
    typer.echo(
        f"Token: {stats['input_tokens']} in, {stats['output_tokens']} out, "
        f"cache {stats['cache_read_tokens']} letti / {stats['cache_write_tokens']} scritti; "
        f"latenza {response.latency_ms} ms; costo {stats['cost_usd']:.5f} USD"
    )
    if response.refused:
        typer.secho(
            "Attenzione: il modello ha rifiutato la richiesta di prova.", fg=typer.colors.YELLOW
        )


@interview_app.command("preview")
def interview_preview(
    config: ConfigOption = Path("config.yaml"),
    mode: Annotated[str, typer.Option("--mode", help="cawi, cati o capi.")] = "cawi",
    n: Annotated[
        int | None, typer.Option("--n", help="Persone da intervistare (default run.pilot_size).")
    ] = None,
    replicate: Annotated[int, typer.Option("--replicate", min=1, help="Numero di replica.")] = 1,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Cartella per responses.csv, responses.json e transcripts."),
    ] = None,
    model_index: Annotated[
        int, typer.Option("--model-index", help="Quale modello di engine.models usare (da 0).")
    ] = 0,
    use_cache: Annotated[
        bool, typer.Option("--cache/--no-cache", help="Riusa le risposte in cache.")
    ] = True,
    data_dir: DataDirOption = Path("data"),
) -> None:
    """Pilota di interviste in una modalità: costruisce le persone e le intervista."""
    import asyncio
    import json
    from collections import Counter

    from synthsurvey.interview import InterviewSpec, run_interview
    from synthsurvey.llm import LLMError, make_pool
    from synthsurvey.personas import build_personas
    from synthsurvey.population.quotas import QuotaError
    from synthsurvey.population.sample import build_sample
    from synthsurvey.population.tables import TablesError, load_tables
    from synthsurvey.questionnaire import Mode, QuestionnaireError, adapt, load_questionnaire

    try:
        cfg = load_config(config).config
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    try:
        modalita = Mode(mode)
    except ValueError:
        typer.secho("--mode deve essere cawi, cati o capi", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from None
    if model_index >= len(cfg.engine.models):
        typer.secho("model-index fuori dalla lista engine.models", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    try:
        loaded_q = load_questionnaire(cfg.questionnaire.path, cfg)
    except QuestionnaireError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    processed = data_dir / "processed"
    n_total = n if n is not None else cfg.run.pilot_size
    try:
        tables = load_tables(processed)
        sample = build_sample(cfg, processed, n_total=n_total, tables=tables)
        personas = build_personas(sample, cfg, tables, processed_dir=processed).personas
    except (TablesError, QuotaError) as exc:
        typer.secho(f"Errore: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    spec_model = cfg.engine.models[model_index]
    pool = make_pool(spec_model, cfg, use_cache=use_cache)
    mq = adapt(loaded_q.questionnaire, modalita)
    run_id = f"preview-{modalita.value}"
    specs = [
        InterviewSpec(
            run_id=run_id,
            persona=p,
            persona_index=i,
            mode=modalita,
            replicate=replicate,
            model=pool.client.model,
            seed=cfg.project.seed,
        )
        for i, p in enumerate(personas)
    ]

    async def _tutte() -> list[object]:
        return list(
            await asyncio.gather(
                *(run_interview(s, loaded_q.questionnaire, mq, pool, cfg) for s in specs)
            )
        )

    try:
        results = asyncio.run(_tutte())
    except LLMError as exc:
        typer.secho(f"Errore LLM: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    except NotImplementedError as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=1) from None

    from synthsurvey.interview import AnswerStatus, InterviewResult

    records = [r for res in results if isinstance(res, InterviewResult) for r in res.records]
    stats = pool.stats.as_dict()
    completate = sum(
        1 for res in results if isinstance(res, InterviewResult) and res.outcome.completed
    )
    typer.secho(
        f"Interviste {modalita.value.upper()}: {len(results)} persone, {completate} completate, "
        f"{len(records)} record",
        fg=typer.colors.GREEN,
    )
    typer.echo(
        f"Chiamate {stats['calls']}, cache {stats['cache_hits']}, rifiuti {stats['refusals']}, "
        f"token {stats['input_tokens']} in / {stats['output_tokens']} out, "
        f"costo {stats['cost_usd']:.4f} USD"
    )
    conte = Counter(r.status for r in records)
    typer.echo(
        "Stati: " + ", ".join(f"{s.value}={conte.get(s, 0)}" for s in AnswerStatus if conte.get(s))
    )
    for q in loaded_q.questionnaire.questions:
        valori = Counter(
            r.answer_text or "-"
            for r in records
            if r.question_id == q.id and r.status is AnswerStatus.ANSWERED
        )
        if valori:
            top = ", ".join(f"{v} x{c}" for v, c in valori.most_common(4))
            typer.echo(f"  {q.id}: {top}")
    avvisi = [
        w for res in results if isinstance(res, InterviewResult) for w in res.outcome.warnings
    ]
    for w in avvisi[:10]:
        typer.secho(f"Avviso: {w}", fg=typer.colors.YELLOW)
    if out is not None:
        import polars as pl

        out.mkdir(parents=True, exist_ok=True)
        righe = [r.to_dict() for r in records]
        for r in righe:
            for k in ("option_order", "nonverbal_emitted", "nonverbal_observed"):
                if r[k] is not None:
                    r[k] = json.dumps(r[k], ensure_ascii=False)
        pl.DataFrame(righe, infer_schema_length=None).write_csv(out / "responses.csv")
        (out / "responses.json").write_text(
            json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        trascrizioni = out / "transcripts"
        trascrizioni.mkdir(exist_ok=True)
        for res in results:
            if not isinstance(res, InterviewResult):
                continue
            nome = f"{res.persona_id}_{modalita.value}_r{replicate}.md"
            testo = "\n\n".join(f"**{t.speaker}**\n\n{t.text}" for t in res.transcript)
            (trascrizioni / nome).write_text(testo + "\n", encoding="utf-8")
        typer.secho(f"Scritto in {out}", fg=typer.colors.GREEN)


@app.command("run")
def run(
    config: ConfigOption = Path("config.yaml"),
    pilot: Annotated[
        bool, typer.Option("--pilot", help="Esegue un pilota su run.pilot_size persone.")
    ] = False,
    run_id: Annotated[
        str | None, typer.Option("--run-id", help="Nome della cartella del run (default: data).")
    ] = None,
    estimate_only: Annotated[
        bool, typer.Option("--estimate-only", help="Solo stima di costo, nessuna chiamata.")
    ] = False,
    use_cache: Annotated[
        bool, typer.Option("--cache/--no-cache", help="Riusa le risposte in cache.")
    ] = True,
    data_dir: DataDirOption = Path("data"),
) -> None:
    """Esegue un run completo: campione, persone, interviste per modalità e replica, output."""
    from synthsurvey.llm import LLMError
    from synthsurvey.population.quotas import QuotaError
    from synthsurvey.population.tables import TablesError
    from synthsurvey.questionnaire import QuestionnaireError
    from synthsurvey.runner import BudgetError, FrozenError, execute_run

    try:
        loaded = load_config(config)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    for w in loaded.warnings:
        typer.secho(f"Avviso: {w.location}: {w.message}", fg=typer.colors.YELLOW)

    def _progress(fatte: int, totali: int, spesa: float) -> None:
        if fatte == totali or fatte % 10 == 0:
            typer.echo(f"  interviste {fatte}/{totali}, spesa {spesa:.2f} EUR")

    try:
        result = execute_run(
            loaded,
            data_dir=data_dir,
            pilot=pilot,
            run_id=run_id,
            use_cache=use_cache,
            progress=_progress,
            estimate_only=estimate_only,
        )
    except BudgetError as exc:
        typer.secho(f"Budget: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=3) from None
    except FrozenError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=4) from None
    except (TablesError, QuotaError, QuestionnaireError, LLMError) as exc:
        typer.secho(f"Errore: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    e = result.estimate
    typer.echo(
        f"Piano: {e.interviews} interviste, circa {e.calls} chiamate, "
        f"stima {e.cost_eur:.2f} EUR su budget {e.budget_eur:.2f} EUR"
    )
    if estimate_only:
        typer.secho("Solo stima: nessuna chiamata eseguita.", fg=typer.colors.GREEN)
        return
    m = result.manifest
    typer.echo(
        f"Interviste fatte {m['interviews_done']}, saltate {m['interviews_skipped']}, "
        f"record {m['records']}, spesa {result.cost_eur:.2f} EUR"
    )
    if result.budget_exceeded:
        typer.secho(
            "Budget superato durante il run: interviste restanti saltate (stato budget_exceeded).",
            fg=typer.colors.YELLOW,
            err=True,
        )
    stato = "congelato" if m.get("frozen") else "non congelato"
    typer.secho(f"Run {result.run_id} in {result.run_dir} ({stato})", fg=typer.colors.GREEN)
    if result.budget_exceeded:
        raise typer.Exit(code=3)


@app.command("freeze")
def freeze(
    run_dir: Annotated[Path, typer.Argument(help="Cartella del run da congelare.")],
    verify: Annotated[
        bool, typer.Option("--verify", help="Verifica gli hash di un run già congelato.")
    ] = False,
) -> None:
    """Congela un run: hash di ogni file nel manifest; da allora nessuna modifica è ammessa."""
    from synthsurvey.runner import freeze_run, is_frozen, verify_frozen

    if verify:
        problemi = verify_frozen(run_dir)
        if problemi:
            for pr in problemi:
                typer.secho(f"  - {pr}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        typer.secho(f"Run congelato e integro: {run_dir}", fg=typer.colors.GREEN)
        return
    if is_frozen(run_dir):
        typer.secho(f"Run già congelato: {run_dir}", fg=typer.colors.YELLOW)
        return
    try:
        manifest = freeze_run(run_dir)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    typer.secho(
        f"Run congelato: {run_dir} ({len(manifest['files'])} file, {manifest['frozen_at']})",
        fg=typer.colors.GREEN,
    )


@app.command("report")
def report(
    run_dir: Annotated[Path, typer.Argument(help="Cartella del run da cui generare il report.")],
) -> None:
    """Genera il report HTML di un run."""
    _non_implementato("report", "M10")


@app.command("validate")
def validate(
    run_dir: Annotated[Path, typer.Argument(help="Cartella del run simulato.")],
    real: Annotated[Path, typer.Option("--real", help="File con le interviste reali.")],
) -> None:
    """Confronta un run simulato con le interviste reali."""
    _non_implementato("validate", "M11")


if __name__ == "__main__":
    app()
