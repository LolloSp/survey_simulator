# Changelog

Tutte le modifiche rilevanti del progetto. Il formato segue
[Keep a Changelog](https://keepachangelog.com/it/1.1.0/); le versioni
seguono il versionamento semantico.

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
