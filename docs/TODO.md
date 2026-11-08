# Da fare

Attività aperte che non rientrano in una milestone o che aspettano una
decisione umana. Una riga per voce; si cancella quando è chiusa.

- [x] **M4, revisione delle 20 persone** (8 novembre 2026, prima passata fatta da Claude,
  da confermare con una lettura tua): coerenza interna e plausibilità buone in 19 casi su 20;
  il difetto vero era una donna di 88 anni "occupata" (l'IPF spalmava gli occupati dei 65+
  anche oltre gli 80). Corretto nel seed (`individui.NO_WORK_AGE = 80`): nessun occupato né
  in cerca da 80 anni in su. Le 20 persone sono state rigenerate. Resta un suggerimento,
  non un difetto: le narrative usano le stesse frasi per tutti (es. "con la gente bisogna
  stare molto attenti"); se con il modello reale le risposte risultano piatte, aggiungere
  varianti di frase al template `persona_it.j2` scelte in modo deterministico dalla persona.
- [ ] **Credito API**: la chiave Anthropic in `.env` è valida ma l'account non ha credito
  (verificato l'8 novembre 2026); finché non viene caricato, i piloti si fanno con il
  provider `session` (M14) e le voci "dal vivo" restano aperte per il modello reale.
- [ ] **M6, prova dal vivo del provider**: con `ANTHROPIC_API_KEY` in `.env`
  lanciare `uv run synthsurvey llm ping --config configs/examples/mercato_100.yaml`
  e verificare credenziali, modello, formato strutturato e costo.
- [x] **M6b, importazione del Word di esempio** (8 novembre 2026): fatta con il provider
  `session` (la trascrizione l'ha scritta Claude nel ruolo dell'agente): YAML valido al primo
  giro, 10 domande, routing dedotto dai salti in prosa, 8 note di incertezza nel rapporto.
  Restano la prova con il modello reale e l'import del questionario vero (vedi M5).
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
