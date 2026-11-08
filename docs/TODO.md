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

- [x] **Provider**: decisione dell'8 novembre 2026, nessun credito API; il modello è la
  sessione di Claude Code (`provider: session`). Gli adapter Anthropic e OpenAI restano
  nel codice ma non sono in uso; le voci "dal vivo" di M6, M12 e la taratura della
  stima costi di M9 decadono.

- [x] **M6b, importazione del Word di esempio** (8 novembre 2026): fatta con il provider
  `session` (la trascrizione l'ha scritta Claude nel ruolo dell'agente): YAML valido al primo
  giro, 10 domande, routing dedotto dai salti in prosa, 8 note di incertezza nel rapporto.
  Resta l'import del questionario vero (vedi M5).

- [x] **M7, pilota CAWI** (8 novembre 2026): completato con il provider `session`, 10 persone,
  120 record validi, routing e stati corretti (`runs/pilota_cawi_sessione`). Senza API non c'è
  altra prova da fare: la plausibilità delle risposte è quella della sessione.

- [x] **M8, piloti CATI e CAPI** (8 novembre 2026): completati con il provider `session`,
  5 persone per modalità (`runs/pilota_cati_sessione`, `runs/pilota_capi_sessione`):
  60 record ciascuno, intervistatore intervenuto 3 e 2 volte (accettazioni su segnali
  moderati, un chiarimento, un rifiuto spontaneo accettato), segnali del corpo solo nel
  CAPI.

- [x] **M9, run pilota** (8 novembre 2026): `run --pilot` con il provider `session`, 5 persone
  x 3 modalità x 1 replica, completato in 7 riprese e congelato (`runs/pilota-sessione`,
  26 file, hash verificati). La stima prevedeva 195 chiamate, ne sono servite 108:
  con il provider sessione il costo è comunque zero, la stima serve solo come ordine di
  grandezza dei giri.

- [ ] **M10, apertura del .sav in SPSS o R**: `runs/pilota-sessione/responses_wide.sav`
  è verificato con pyreadstat; serve una macchina con R (`haven::read_sav`) o SPSS,
  qui non ci sono. Tocca a te, oppure autorizza l'installazione di R su questo PC.

- [ ] **M11, validazione con dati veri**: esportare le interviste reali del caso
  di riferimento nel formato lungo (docs/methodology.md, sezione 9) e lanciare
  `synthsurvey validate`; il criterio della SPEC è verificato finora solo con
  un dataset fittizio.

- [ ] **Release su GitHub**: creare la release dal tag più recente con il testo di
  `CHANGELOG.md` (dal browser: Releases, Draft a new release).

- [ ] **M13, prepare sull'anagrafica vera via sessione**: `prepare --provider session`
  sul file in `data/raw/` con il questionario di esempio allineato ai segmenti
  `privati`/`imprese`, poi `run --pilot` con poche persone per modalità rispondendo
  dalla sessione; verificare che le narrative delle imprese con rispondente noto dal
  codice fiscale siano coerenti.

- [ ] **M5, questionario reale**: caricare il questionario già pronto del
  caso di riferimento in `questionnaires/` e verificare che le tre versioni
  per modalità siano esportabili per revisione (criterio di M5).
