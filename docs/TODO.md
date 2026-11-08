# Da fare

Attività aperte che non rientrano in una milestone o che aspettano una
decisione umana. Una riga per voce; si cancella quando è chiusa.

- [ ] **M4, revisione manuale delle 20 persone** (`docs/examples/personas_20.md`):
  verificare coerenza interna, plausibilità, qualità del testo, varietà e
  ragionevolezza delle ipotesi. Esiti possibili: correzioni al template
  `src/synthsurvey/agents/prompts/persona_it.j2`, ai priori
  `src/synthsurvey/personas/priors/default.yaml`, o nuove regole in
  `src/synthsurvey/personas/coherence.py`. Finché non è fatta, M4 è
  implementata ma non chiusa secondo il criterio della SPEC. Aperta il
  6 novembre 2026, si procede intanto con M5 per decisione del responsabile.
- [ ] **Credito API**: la chiave Anthropic in `.env` è valida ma l'account non ha credito
  (verificato l'8 novembre 2026); finché non viene caricato, i piloti si fanno con il
  provider `session` (M14) e le voci "dal vivo" restano aperte per il modello reale.
- [ ] **M6, prova dal vivo del provider**: con `ANTHROPIC_API_KEY` in `.env`
  lanciare `uv run synthsurvey llm ping --config configs/examples/mercato_100.yaml`
  e verificare credenziali, modello, formato strutturato e costo.
- [ ] **M6b, importazione dal vivo**: lanciare `questionnaire import` sul Word di
  esempio `questionnaires/examples/mercato_v1.docx` e poi su un questionario
  vero del caso di riferimento; leggere il rapporto `.import.md`, correggere lo
  YAML a mano e confrontarlo con `questionnaires/examples/mercato_v1.yaml`.
  Esiti possibili: ritocchi al prompt `questionnaire_import_it.j2`. Finché non è
  fatta, M6b è implementata ma non chiusa secondo il criterio della SPEC.
- [ ] **M7, pilota CAWI dal vivo**: con la chiave in `.env` lanciare
  `uv run synthsurvey interview preview --config configs/examples/mercato_100.yaml --mode cawi --n 10 --out runs/pilota_cawi`
  e leggere `responses.csv` e le trascrizioni: risposte piatte, incoerenti o
  troppo articolate per il profilo sono il segnale per ritoccare
  `respondent_it.j2`. Il criterio di M7 (pilota da 10 persone con risposte
  valide) è verificato solo con il client finto.
- [ ] **M8, piloti CATI e CAPI dal vivo**: come per M7 con `--mode cati` e
  `--mode capi`; leggere le trascrizioni in `transcripts/` e la colonna
  `incongruence`: se l'intervistatore interviene troppo o troppo poco, agire
  sulla soglia `PROBE_THRESHOLD` o sul prompt `interviewer_it.j2`.
- [ ] **M9, run pilota dal vivo**: `uv run synthsurvey run --config configs/examples/mercato_100.yaml --pilot`
  con la chiave in `.env`; confrontare la spesa reale nel manifest con la stima
  e, se la stima sbaglia di molto, ritoccare le costanti in `runner/plan.py`.
- [ ] **M10, apertura del .sav in SPSS o R**: il file è verificato con pyreadstat;
  il criterio della SPEC chiede l'apertura in SPSS o R (`haven::read_sav`) su un
  run vero. Da fare quando esiste un run con il modello reale.
- [ ] **M11, validazione con dati veri**: esportare le interviste reali del caso
  di riferimento nel formato lungo (docs/methodology.md, sezione 9) e lanciare
  `synthsurvey validate`; il criterio della SPEC è verificato finora solo con
  un dataset fittizio.
- [ ] **M12, prova dal vivo di OpenAI**: con `OPENAI_API_KEY` in `.env` lanciare
  `uv run synthsurvey llm ping --config configs/examples/mercato_100_ensemble.yaml --model-index 1`;
  verificare che `reasoning_effort` e `response_format` strict siano accettati dal
  modello scelto e confrontare la spesa con la tabella prezzi (`llm/prices.yaml`,
  da aggiornare se i listini sono cambiati).
- [ ] **Release v0.1.0 su GitHub**: creare la release dal tag `v0.1.0` con il testo
  di `CHANGELOG.md`.
- [ ] **M13, prepare sull'anagrafica vera con il modello reale**: con la chiave in `.env`
  lanciare `prepare` sul file in `data/raw/` e sul questionario del caso, leggere
  `contacts_report.json` (scarti e motivi) e il rapporto d'importazione, poi `run --pilot`.
  Verificare che le narrative delle imprese con rispondente noto siano coerenti.
- [ ] **M5, questionario reale**: caricare il questionario già pronto del
  caso di riferimento in `questionnaires/` e verificare che le tre versioni
  per modalità siano esportabili per revisione (criterio di M5).
