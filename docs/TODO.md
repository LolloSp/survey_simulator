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

- [x] **M10, apertura del .sav in R** (8 novembre 2026): installato R 4.6.2 con winget e
  letto con `haven::read_sav(user_na = TRUE)` sia `runs/pilota-sessione/responses_wide.sav`
  (15 righe, 36 colonne) sia quello del pilota sull'anagrafica (12 righe): 17 variabili con
  etichette di valore, 16 con i missing -1/-2/-3/-4 dichiarati, nessuna variabile senza
  etichetta; le frequenze di `q1` coincidono con il formato lungo. SPSS non provato.

- [ ] **M11, validazione con dati veri**: esportare le interviste reali del caso
  di riferimento nel formato lungo (docs/methodology.md, sezione 9) e lanciare
  `synthsurvey validate`; il criterio della SPEC è verificato finora solo con
  un dataset fittizio.

- [x] **Release su GitHub** (8 novembre 2026): tag `v0.1.2` creato sul commit di M14 e
  release v0.1.0, v0.1.1 e v0.1.2 pubblicate con `gh release create` e le sezioni di
  `CHANGELOG.md` (v0.1.2 marcata Latest). Il repository è pubblico: da confermare se voluto
  per un prodotto proprietario (`gh repo edit --visibility private`).

- [x] **M13, prepare sull'anagrafica vera via sessione** (8 novembre 2026): `prepare
  --provider session --size 3 --modes cawi,cati` sul file in `data/raw/` (2231 record
  validi, 955 privati e 1276 imprese) con il questionario di esempio rimappato sui segmenti
  `privati`/`imprese`; `run --pilot` da 6 persone x 2 modalità completato in 9 riprese e
  congelato (`runs/progetti/forniture/runs/pilota`, 25 file). Verificato: nomi sintetici,
  mappa persona-record solo in `private/`, provenienza `anagrafica` nel codebook, narrative
  delle tre imprese coerenti con sesso, età e ruolo dedotti dal codice fiscale
  (amministratore con 4 addetti, due titolari con 5 e 6). Limite noto: l'anagrafica non
  porta il titolo di studio, che l'ISTAT completa in modo plausibile ma uniforme.

- [x] **M5, questionario reale** (8 novembre 2026): `Gerarchia Messaggi.xlsx` importato via
  sessione con `prepare` insieme all'anagrafica (progetto in `runs/progetti/gerarchia_messaggi`,
  12 interviste stimate): traccia qualitativa di 7 domande aperte per consumatori e imprese,
  con rilancio e nota di codifica per domanda. YAML valido al primo giro, tre versioni per
  modalità esportate in `runs/progetti/gerarchia_messaggi/export/`. Il questionario del
  committente è un dato di input e non si versiona: `questionnaires/` è ignorata tranne
  `examples/`.

- [x] **Run sul questionario reale** (8 novembre 2026): 20 clienti in proporzione all'anagrafica
  (9 privati, 11 imprese) × CAWI, CATI e CAPI, provider sessione, 60 interviste completate e
  congelate in `runs/progetti/gerarchia_messaggi_20/`. Limite noto: dalla domanda 3 in poi i
  segnali non verbali hanno un tono fisso per persona e modalità.

- [x] **Pagina `interviste.html`** (8 novembre 2026, richiesta da Lorenzo): sempre prodotta con il
  report; specifica in SPEC.md, sezione «Contenuto di ogni cartella di run».

- [x] **Rilanci dell'intervistatore** (8 novembre 2026, deciso da Lorenzo): aggiunti `probe` e `coding_note` alla domanda, rilancio da copione nel dialogo CATI/CAPI, `probe_text` nel record; il questionario reale li usa su tutte le 7 domande. Il segmento `privati` resta: il questionario è per consumatori e imprese, quindi senza `applies_to`.
