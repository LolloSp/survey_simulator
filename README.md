# synthsurvey

Simulatore di indagini su popolazione sintetica italiana. Genera un campione di
rispondenti coerente con i dati ISTAT e gli sottopone un questionario in tre
modalità (CAWI, CATI, CAPI) tramite agenti LLM, producendo un dataset con pesi,
paradati e codebook.

Specifica completa: [docs/SPEC.md](docs/SPEC.md). Stato: **M4 – persone**.

## Avvio rapido

```bash
uv python install 3.12
uv sync
uv run synthsurvey --help
```

Validare una configurazione (esempi in `configs/examples/`):

```bash
uv run synthsurvey config validate configs/examples/mercato_100.yaml
```

Scaricare e verificare le tavole ISTAT (le tavole normalizzate sono già nel repo in `data/processed/`):

```bash
uv run synthsurvey data fetch            # tutte le tavole, cache in data/raw/
uv run synthsurvey data fetch --offline  # rigenera dalla cache senza rete
uv run synthsurvey data status           # elenco e verifica degli hash
```

Costruire e ispezionare il campione (quote, celle piccole, pesi):

```bash
uv run synthsurvey sample preview --config configs/examples/mercato_100.yaml --out runs/preview
```

Generare le persone (attributi, stile di risposta, narrativa) e salvarle per revisione:

```bash
uv run synthsurvey personas preview --config configs/examples/mercato_100.yaml --n 20 --out runs/personas
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
