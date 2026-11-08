# Changelog

Tutte le modifiche rilevanti del progetto. Il formato segue
[Keep a Changelog](https://keepachangelog.com/it/1.1.0/); le versioni
seguono il versionamento semantico.

## [0.1.4] - 2026-11-08

### Aggiunto

- Pagina `interviste.html`, prodotta sempre accanto a `report.html` (a fine run e da `synthsurvey report`): un file autonomo per leggere interviste e risposte per domanda o per persona, con modalità affiancate, rilanci, filtri per segmento e replica, ricerca e segnali non verbali a richiesta. Nessun dato del committente.

## [0.1.3] - 2026-11-08

### Aggiunto

- Rilanci da copione: campi `probe` e `coding_note` sulla domanda; in CATI e CAPI l'intervistatore legge il rilancio una volta dopo la risposta spontanea, la risposta successiva va in `probe_text`; export, importazione e codebook li riportano.

## [0.1.2] - 2026-11-08

### Aggiunto

- Provider `session` (M14): il modello è la sessione di Claude Code; richieste in attesa su
  file, comandi `session list` e `session answer`, run e piloti che si sospendono (codice 5) e
  riprendono dallo stesso comando. Esempio `configs/examples/pilota_sessione.yaml`.

## [0.1.1] - 2026-11-08

### Aggiunto

- Sorgente `lista_clienti`: il campione è l'anagrafica del committente (Excel o CSV con
  intestazioni variabili); ISTAT completa gli attributi mancanti; provenienza `anagrafica` (M13).
- Comando `synthsurvey prepare`: da questionario e anagrafica alla configurazione pronta,
  con rapporto dei record e stima del run.
- Skill di progetto `synthsurvey-run` per condurre un run da una sessione di Claude Code.
- Tabella delle province italiane nel pacchetto.

### Sicurezza

- Nomi, codici fiscali e contatti dell'anagrafica non entrano in campione, prompt o output;
  la corrispondenza persona-record sta in `<run>/private/`.

## [0.1.0] - 2026-11-07

Prima release interna: la catena completa da configurazione a report.

### Aggiunto

- Configurazione YAML validata con messaggi chiari (M1).
- Tavole ISTAT via API SDMX, normalizzate e versionate con hash (M2).
- Popolazione sintetica via IPF, campione per quote, sovracampionamento,
  pesi e controllo delle celle piccole (M3).
- Persone con atteggiamenti, stile di risposta e narrativa in italiano,
  con provenienza di ogni tratto (M4).
- Questionario strutturato con routing `show_if`, adattamento automatico
  per modalità ed esportazione per revisione (M5).
- Livello LLM: client astratto, adapter Anthropic, cache, retry, costi (M6).
- Importazione del questionario grezzo da Word, PDF, Excel con agente LLM e
  rapporto delle incertezze (M6b).
- Interviste CAWI una pagina alla volta (M7); CATI e CAPI con intervistatore,
  segnali non verbali e trascrizioni (M8).
- Runner con piano, stima dei costi, budget, cache riavviabile, manifest e
  congelamento (M9).
- Dataset largo, .sav con etichette, codebook e report HTML (M10).
- Validazione contro dati reali con metriche e rapporto di confronto (M11).
- Adapter OpenAI, ensemble di modelli con divergenza nel report, esempio di
  configurazione a due provider, documentazione (M12).

### Note

- Le prove dal vivo con i modelli reali e la revisione manuale delle persone
  restano aperte: vedi `docs/TODO.md`.
