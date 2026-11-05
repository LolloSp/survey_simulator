# synthsurvey

Simulatore di indagini su popolazione sintetica italiana.
Specifica completa: docs/SPEC.md. Leggila prima di ogni milestone.

## Regole
- Lavora una milestone alla volta (vedi Roadmap in SPEC.md).
  Prima di scrivere codice, proponi un piano e aspetta conferma.
- Non passare alla milestone successiva finché i criteri "Fatto quando"
  non sono soddisfatti e la CI è verde. Un commit per milestone.
- Nessun parametro di campione o di questionario nel codice: tutto da config.
- Ogni modulo ha test; nei test usa sempre il client LLM finto,
  mai chiamate reali.
- Riproducibilità: ogni casualità passa dal seed della config.
- Un run congelato non si modifica mai.
- Prompt degli agenti in file separati (src/synthsurvey/agents/prompts/),
  in italiano, versionati.
- Chiavi API solo da variabili d'ambiente (.env non versionato).
- Se una scelta cambia durante il lavoro, aggiorna prima SPEC.md
  e poi il codice: il documento resta la fonte di verità.
- Codice, commenti, docstring e messaggi della CLI in italiano;
  nomi di identificatori in inglese.

## Comandi
- uv run pytest
- uv run ruff check . && uv run ruff format --check . && uv run mypy src
- uv run synthsurvey --help
- uv run synthsurvey data status  (verifica hash delle tavole ISTAT; `data fetch` usa la rete)
- uv run python scripts/istat_explore.py search <parola>  (ricognizione dataflow ISTAT)

## Ambiente
- Sviluppo su Windows 11 (PowerShell); la CI gira su Linux.
  I percorsi passano sempre da pathlib, mai stringhe con separatori fissi.
- Python 3.12 gestito da uv (`uv python install 3.12`).
