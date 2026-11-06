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
- [ ] **M5, questionario reale**: caricare il questionario già pronto del
  caso di riferimento in `questionnaires/` e verificare che le tre versioni
  per modalità siano esportabili per revisione (criterio di M5).
