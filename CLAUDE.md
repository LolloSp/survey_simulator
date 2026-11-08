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
- Anagrafiche dei committenti: mai nomi, codici fiscali o contatti nei prompt,
  negli output o nella conversazione; i file restano in data/raw (non versionata).
- Se una scelta cambia durante il lavoro, aggiorna prima SPEC.md
  e poi il codice: il documento resta la fonte di verità.
- Codice, commenti, docstring e messaggi della CLI in italiano;
  nomi di identificatori in inglese.

## Comandi
- uv run pytest
- uv run pytest --network  (aggiunge il test che chiama davvero l'API ISTAT)
- uv run ruff check . && uv run ruff format --check . && uv run mypy src
- uv run synthsurvey --help
- uv run synthsurvey data status  (verifica hash delle tavole ISTAT; `data fetch` usa la rete)
- uv run synthsurvey sample preview --config configs/examples/mercato_100.yaml
- uv run synthsurvey personas preview --config configs/examples/mercato_100.yaml --n 20
- uv run synthsurvey questionnaire validate questionnaires/examples/mercato_v1.yaml --config configs/examples/mercato_100.yaml
- uv run synthsurvey llm ping --config configs/examples/mercato_100.yaml  (una chiamata reale: costa, usa la chiave in .env)
- uv run synthsurvey questionnaire import questionnaires/examples/mercato_v1.docx --config configs/examples/mercato_100.yaml --out runs/importato/mercato_v1.yaml  (chiamate reali)
- uv run synthsurvey interview preview --config configs/examples/mercato_100.yaml --mode cawi --n 10 --out runs/pilota_cawi  (chiamate reali)
- uv run synthsurvey run --config configs/examples/mercato_100.yaml --pilot --estimate-only  (stima senza chiamate)
- uv run synthsurvey run --config configs/examples/mercato_100.yaml --pilot  (chiamate reali, poi `freeze <cartella>`)
- uv run synthsurvey report <cartella del run> --out <altra cartella>  (rigenera gli output; nessuna chiamata)
- uv run synthsurvey validate <cartella del run> --real <csv> --out <cartella>  (confronto con dati reali; nessuna chiamata)
- uv run synthsurvey run --config configs/examples/mercato_100_ensemble.yaml --pilot --estimate-only  (ensemble a due provider)
- uv run synthsurvey prepare --questionnaire <file> --contacts <file> --out progetti/<nome>  (anagrafica + questionario -> config; stima senza chiamate)
- uv run python scripts/make_questionnaire_fixtures.py  (rigenera il Word di esempio e il PDF dei test)
- uv run python scripts/istat_explore.py search <parola>  (ricognizione dataflow ISTAT)

## Ambiente
- Sviluppo su Windows 11 (PowerShell); la CI gira su Linux.
  I percorsi passano sempre da pathlib, mai stringhe con separatori fissi.
- Python 3.12 gestito da uv (`uv python install 3.12`).
