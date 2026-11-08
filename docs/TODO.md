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
- [x] **M7, pilota CAWI** (8 novembre 2026): completato con il provider `session`, 10 persone,
  120 record validi, routing e stati corretti (`runs/pilota_cawi_sessione`). Resta la
  prova con il modello reale quando c'è credito: `interview preview --mode cawi` sulla
  config `mercato_100.yaml`, per giudicare la plausibilità delle risposte del modello.
- [x] **M8, piloti CATI e CAPI** (8 novembre 2026): completati con il provider `session`,
  5 persone per modalità (`runs/pilota_cati_sessione`, `runs/pilota_capi_sessione`):
  60 record ciascuno, intervistatore intervenuto 3 e 2 volte (accettazioni su segnali
  moderati, un chiarimento, un rifiuto spontaneo accettato), segnali del corpo solo nel
  CAPI. Resta la prova con il modello reale.
- [x] **M9, run pilota** (8 novembre 2026): `run --pilot` con il provider `session`, 5 persone
  x 3 modalità x 1 replica, completato in 7 riprese e congelato (`runs/pilota-sessione`,
  26 file, hash verificati). La stima prudente prevedeva 195 chiamate, ne sono servite
  108: le costanti in `runner/plan.py` sopravvalutano di circa l'80%, da tarare con il
  modello reale (la spesa reale resta da confrontare quando c'è credito).
- [ ] **M10, apertura del .sav in SPSS o R**: il file `runs/pilota-sessione/responses_wide.sav`
  esiste ed è verificato con pyreadstat; su questo PC non ci sono né R né SPSS. Da aprire
  su una macchina con R (`haven::read_sav`) o SPSS: tocca a te.
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
