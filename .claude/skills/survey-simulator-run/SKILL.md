---
name: survey-simulator-run
description: Conduce una simulazione d'indagine survey_simulator da una sessione di Claude Code a partire da un questionario (YAML, Word, PDF o Excel) e da un file di anagrafiche del committente (Excel o CSV). Usare quando l'utente chiede di lanciare, preparare o simulare un'indagine, un sondaggio o interviste sintetiche su un elenco di clienti.
---

# Condurre un run di survey_simulator da questionario e anagrafica

Tu guidi la sessione; i comandi fanno il lavoro. Non scrivere mai dati
personali dell'anagrafica (nomi, codici fiscali, email, telefoni) nella
conversazione, nei file del progetto versionati o nei prompt: il prodotto
li tiene fuori e tu fai lo stesso. Se l'utente incolla righe con dati
personali, non ripeterle.

## 1. Raccogli i due file

Chiedi, se non li hai già:
- il questionario: YAML strutturato oppure Word/PDF/Excel grezzo;
- l'anagrafica: Excel o CSV con almeno sesso o codice fiscale, età o data
  di nascita o codice fiscale, e provincia, regione o codice ISTAT del
  comune. Per le imprese bastano partita IVA, provincia e codice ATECO.

I file stanno in `data/raw/` (non versionata) o dove indica l'utente.
Verifica che `.env` contenga la chiave del provider (`ANTHROPIC_API_KEY`
o `OPENAI_API_KEY`): senza chiave fermati e chiedila.

## 2. Prepara il progetto

```
uv run survey-simulator prepare --questionnaire <file> --contacts <file> --out progetti/<nome>
```

Opzioni utili: `--size 100` per un sottocampione casuale per segmento quando
l'anagrafica è grande (la stima con il modello reale lo dirà subito);
`--mapping sex=Genere,age=Eta` se le colonne non vengono riconosciute; `--sheet` per un foglio Excel specifico; `--provider`,
`--model`, `--modes`, `--replicates`, `--budget`, `--project-name`.

Leggi l'output e riferisci all'utente, in poche righe:
- righe lette, record validi, scarti e motivi (`contacts_report.json`);
- segmenti creati (`privati`, `imprese`) e numerosità;
- se il questionario è stato importato dall'agente: va rivisto prima del
  run, con il rapporto `.import.md` accanto allo YAML;
- la stima di interviste e costo rispetto al budget.

Se `prepare` si ferma: colonne non riconosciute → proponi `--mapping` dopo
aver visto le intestazioni (chiedile, non leggere il file tu); questionario
importato non valido → correggi lo YAML seguendo il rapporto e rilancia
`prepare` indicando lo YAML; stima oltre il budget → proponi `--budget`
più alto, meno repliche o meno modalità.

## 3. Fai confermare e lancia il pilota

Prima di spendere, mostra la stima e chiedi conferma esplicita. Poi:

```
uv run survey-simulator run --config progetti/<nome>/config.yaml --pilot
```

Apri `report.html` nella cartella del run e riassumi: completamento per
modalità, distribuzioni delle prime domande, incongruenze non verbali,
spesa reale contro stima. Leggi una trascrizione CATI o CAPI e giudica se
le risposte sono plausibili per il profilo. Se qualcosa non va, è il
momento di correggere il questionario o la configurazione.

## 4. Run completo, poi congela

Con il via libera dell'utente:

```
uv run survey-simulator run --config progetti/<nome>/config.yaml
uv run survey-simulator freeze <cartella del run>
```

Consegna all'utente i percorsi di `report.html`, `interviste.html` (interviste e
risposte da leggere, per domanda o per persona), `responses_wide.sav`,
`codebook.json`. Ricorda che `private/contacts_map.csv` lega le persone ai
record dei clienti e non va condiviso.

## 5. Quando arrivano i dati reali

```
uv run survey-simulator validate <cartella del run> --real <csv> --out <cartella>
```

Il formato del CSV è in `docs/methodology.md`, sezione 9.

## Senza credito API: il provider sessione

Se non c'è una chiave o il credito, il modello sei tu. Nella configurazione
`engine.models` deve avere `provider: session`, `model: session` (esempio:
`configs/examples/pilota_sessione.yaml`). Il ciclo è:

1. lancia il comando (`interview preview ...` oppure `run --pilot`): si ferma
   con codice 5 e dice quante richieste aspettano;
2. `uv run survey-simulator session list --config <config> --full --out <file.md>` e
   leggi il file: per ogni richiesta trovi system prompt (la persona e le
   regole della modalità), la conversazione e lo schema JSON della risposta;
3. rispondi **come quella persona**, seguendo le regole del system prompt
   (tempo disponibile, acquiescenza, "non so", stile): niente risposte da
   assistente, niente perfezione; scrivi un file JSON `impronta -> oggetto
   conforme allo schema` e depositalo con `survey-simulator session answer
   <file.json> --config <config>`; le risposte non conformi vengono
   rifiutate con il motivo;
4. rilancia lo stesso comando del punto 1; ripeti finché completa.

Ogni passo sequenziale (una pagina CAWI, una domanda CATI o CAPI) richiede
un giro: un pilota CAWI da 10 persone sono 5-7 giri, un CATI 10-15. Va bene
per decine di interviste, non per i run completi. Il costo è il contesto
della sessione: tienilo basso rispondendo in blocco e senza ricopiare i
prompt nella chat.

## Regole

- Un passo alla volta, con conferma prima di ogni spesa.
- Tutti i parametri stanno in `config.yaml`: non modificare il codice per un
  progetto.
- Le cartelle dei run congelati non si toccano: correzioni = nuovo run.
