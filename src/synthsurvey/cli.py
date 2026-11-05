"""Interfaccia a riga di comando di synthsurvey.

I comandi sono registrati qui ma implementati nelle rispettive milestone
(vedi docs/SPEC.md, sezione Roadmap). Finché non sono implementati
stampano un avviso ed escono con codice 1.
"""

from pathlib import Path
from typing import Annotated

import typer

from synthsurvey import __version__

app = typer.Typer(
    name="synthsurvey",
    help="Simulatore di indagini su popolazione sintetica italiana.",
    no_args_is_help=True,
    add_completion=False,
)
data_app = typer.Typer(help="Gestione delle tabelle sorgente ISTAT.", no_args_is_help=True)
sample_app = typer.Typer(help="Popolazione sintetica e campione.", no_args_is_help=True)
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


@data_app.command("fetch")
def data_fetch(config: ConfigOption = Path("config.yaml")) -> None:
    """Scarica e normalizza le tabelle ISTAT indicate nella configurazione."""
    _non_implementato("data fetch", "M2")


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
