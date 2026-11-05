# synthsurvey

Simulatore di indagini su popolazione sintetica italiana. Genera un campione di
rispondenti coerente con i dati ISTAT e gli sottopone un questionario in tre
modalità (CAWI, CATI, CAPI) tramite agenti LLM, producendo un dataset con pesi,
paradati e codebook.

Specifica completa: [docs/SPEC.md](docs/SPEC.md). Stato: **M0 – scheletro**.

## Avvio rapido

```bash
uv python install 3.12
uv sync
uv run synthsurvey --help
```

## Sviluppo

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pre-commit install
```

Le chiavi API si leggono solo da variabili d'ambiente: copiare `.env.example`
in `.env` e compilarlo.

## Avvertenza

I risultati sono **simulati** e servono a pre-testare questionari, esplorare
ipotesi e stimare effetti di modalità. Non sostituiscono un'indagine reale.

Software proprietario, tutti i diritti riservati. Dati di fonte ISTAT soggetti
ai relativi termini d'uso.
