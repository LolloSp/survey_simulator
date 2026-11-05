"""Interfaccia a riga di comando di synthsurvey.

I comandi sono registrati qui ma implementati nelle rispettive milestone
(vedi docs/SPEC.md, sezione Roadmap). Finché non sono implementati
stampano un avviso ed escono con codice 1.
"""

from pathlib import Path
from typing import Annotated

import typer

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
app.add_typer(config_app, name="config")
app.add_typer(data_app, name="data")
app.add_typer(sample_app, name="sample")

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
    if loaded.warnings:
        typer.secho(f"Avvisi ({len(loaded.warnings)}):", fg=typer.colors.YELLOW)
        for w in loaded.warnings:
            typer.secho(f"  - {w.location}: {w.message}", fg=typer.colors.YELLOW)


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
def sample_preview(config: ConfigOption = Path("config.yaml")) -> None:
    """Mostra marginali e celle di quota del campione senza generare persone."""
    _non_implementato("sample preview", "M3")


@app.command("run")
def run(
    config: ConfigOption = Path("config.yaml"),
    pilot: Annotated[
        bool, typer.Option("--pilot", help="Esegue un pilota su un sottoinsieme ridotto.")
    ] = False,
) -> None:
    """Esegue un run completo: campione, interviste nelle modalità previste, repliche."""
    _non_implementato("run --pilot" if pilot else "run", "M9")


@app.command("freeze")
def freeze(
    run_dir: Annotated[Path, typer.Argument(help="Cartella del run da congelare.")],
) -> None:
    """Congela un run: modello, prompt, parametri, seed e versioni dei dati."""
    _non_implementato("freeze", "M9")


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
