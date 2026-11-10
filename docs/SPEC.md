# Simulatore di indagini su popolazione sintetica italiana — Specifica di progetto

Nov 5, 2026 · @Lorenzo Spanu

**Nome.** Il progetto si chiama `survey_simulator` (fino alla v0.1.4 si chiamava `synthsurvey`; rinominato il 10 novembre 2026). Il pacchetto Python è `survey_simulator`, il comando da terminale `survey-simulator`, il repository GitHub `LolloSp/survey_simulator`. Il manifest dei run scrive la versione del pacchetto in `survey_simulator_version`; i run prodotti prima della rinomina restano validi e riportano `synthsurvey_version`, chiave che nessun comando legge.

## Visione e ambito

Il prodotto genera un campione sintetico di rispondenti italiani a partire dai dati ISTAT e gli sottopone un questionario in tre modalità: form online (CAWI), telefono (CATI) e di persona (CAPI). Ogni rispondente è un agente LLM con un profilo coerente con la popolazione reale. L'output è un dataset analizzabile con pesi, paradati e codebook.

È un prodotto "a scaffale", in un repository privato su GitHub, riutilizzabile su progetti diversi cambiando solo configurazione e questionario.

**Obiettivi**

- Campione parametrico: dimensione totale (100, 500, 1.000…), segmenti (consumer, PMI, altri) e caratteristiche di ciascun segmento decisi da configurazione.
- Simulazione credibile delle tre modalità, inclusi gli effetti di modalità documentati in letteratura.
- Riproducibilità completa: ogni esecuzione è ricostruibile da configurazione, versione dei dati e seed.
- Confronto ex post con interviste reali tramite un modulo di validazione con metriche definite in anticipo.

**Fuori ambito (v1)**

- Sostituire un'indagine reale: il prodotto serve a pre-testare questionari, esplorare ipotesi e stimare effetti di modalità.
- Interfaccia web completa: la v1 è una CLI; una UI può arrivare dopo.
- Voce sintetica: CATI e CAPI sono simulati come dialoghi testuali.

**Primo caso d'uso di riferimento:** ricerca di mercato su popolazione italiana generale, 100 rispondenti (70 consumer, 30 PMI), questionario già pronto, interviste reali successive con modalità ancora da decidere.

## Glossario

| Termine | Significato nel progetto |
| --- | --- |
| Popolazione sintetica | Insieme di individui o imprese generati per rispettare le distribuzioni ISTAT |
| Segmento | Tipologia di rispondente (consumer, PMI, altro) con regole di quota proprie |
| Persona | Profilo di un singolo rispondente: dati demografici, atteggiamenti, stile di risposta |
| Agente rispondente | LLM che risponde al questionario impersonando una persona |
| Agente intervistatore | LLM che conduce l'intervista in CATI e CAPI |
| CAWI / CATI / CAPI | Form web / intervista telefonica / intervista di persona |
| Effetto di modalità | Differenza nelle risposte dovuta al canale, non al rispondente |
| Run | Una esecuzione completa: campione + questionario + modalità + repliche |
| Replica | Ripetizione della stessa intervista per misurare la variabilità del modello |
| Congelamento | Blocco di modello, prompt, parametri e seed prima delle interviste reali |
| Paradati | Dati sul processo: durata simulata, abbandoni, richieste di chiarimento |

## Architettura

Il sistema è una pipeline a moduli indipendenti: ognuno legge un input tipizzato e produce un output salvato su disco, così ogni passo si testa e si riesegue da solo.

&#91;embedded content: architettura · dal file di configurazione alla validazione\]

Il Runner è il cuore: prende persone e versioni del questionario, lancia le interviste nelle modalità previste e passa per il livello LLM, unico punto di contatto con i provider. Le interviste reali entrano solo alla fine, nel modulo di validazione.

## Configurazione parametrica

Tutto ciò che cambia tra un progetto e l'altro sta in un unico file YAML, validato all'avvio. Il codice non contiene mai numeri di campione o caratteristiche dei segmenti.

```yaml
project:
  name: indagine-mercato-2026
  seed: 20261105

sample:
  total: 100
  allocation: quota            # quota | proportional
  segments:
    consumer:
      share: 0.70              # oppure size: 70
      source: istat_individui
      filters:
        age: [18, 99]
        region: all
      quotas: [sex, age_band, macro_area, education, employment]
      oversample: {}
    pmi:
      share: 0.30
      source: istat_imprese
      filters:
        employees: [1, 249]
        sectors: all
      quotas: [size_class, sector, macro_area]
      oversample:
        size_class: {micro: 0.4, piccola: 0.35, media: 0.25}
      respondent_role: [titolare, responsabile_acquisti, amministratore]

questionnaire:
  path: questionnaires/mercato_v1.yaml

# In alternativa ai segmenti ISTAT, il campione può essere un'anagrafica del
# committente (M13): ISTAT completa ciò che il file non dice.
# sample:
#   total: null                  # null = tutti i record validi
#   segments:
#     clienti_privati:
#       source: lista_clienti
#       contacts:
#         path: data/raw/anagrafica.xlsx
#         unit: individui        # individui | imprese
#         sheet: null            # primo foglio
#         mapping: {}            # colonna canonica -> intestazione, se il riconoscimento fallisce
#         keep: {IDTipologiaCliente: [C]}   # righe da tenere: colonna -> valori ammessi
#       size: null               # sottocampione casuale dal seed, se indicato

personas:
  priors_path: null            # YAML con i priori dei tratti senza fonte ISTAT (default nel pacchetto)
  include_names: true          # nome di battesimo nella narrativa

modes:
  design: within_subject       # within_subject | between_subject
  enabled: [cawi, cati, capi]
  allocation: {cawi: 0.34, cati: 0.33, capi: 0.33}   # solo between_subject

engine:
  models:                      # piu modelli = ensemble
    - provider: anthropic      # anthropic | fake (test) | openai (M12)
      model: claude-opus-5-5   # default; Sonnet 5.5 e Haiku 5.5 per contenere i costi; provider session (M14) per piloti senza API
  effort: low                  # low | medium | high: profondità di ragionamento del modello
  max_tokens: 1024             # per singola risposta
  concurrency: 4               # chiamate in parallelo
  timeout_s: 120
  cache_dir: null              # default <output.dir>/.cache
  eur_per_usd: 0.92            # cambio per il budget in euro
  temperature: null            # solo per provider che la supportano: i modelli Claude attuali la rifiutano
  replicates: 3
  randomize_option_order: true
  nonverbal:
    enabled: true              # solo CATI e CAPI
    vocabulary: default

run:
  pilot: false
  pilot_size: 12               # persone nel pilota (10-15 consigliate)
  frozen: false                # true blocca qualsiasi modifica
  budget_max_eur: 50

output:
  formats: [parquet, csv, sav]
  dir: runs/
```

**Regole di validazione della configurazione**

- Le quote dei segmenti sommano a 1 (o le dimensioni al totale).
- Avviso se una cella di quota prevista ha meno di 3 casi, con proposta di accorpamento delle categorie.
- Blocco delle combinazioni impossibili (ad esempio titolare di media impresa sotto i 20 anni).
- Stima di costo e tempo prima del lancio; stop se supera `budget_max_eur`.
- Nuovi segmenti (ad esempio "grandi imprese" o "pubblica amministrazione") si aggiungono con una nuova sorgente dati, senza toccare il resto del codice.

## Metodologia

### 1. Popolazione e campione

- **Fonti consumer:** tavole ISTAT su popolazione residente (Censimento permanente) e indagini come Aspetti della vita quotidiana ed EU-SILC, usando dati aggregati pubblici e file di microdati ad uso pubblico dove disponibili.
- **Fonti PMI:** Censimento permanente delle imprese e registro ASIA (imprese attive per settore Ateco, classe di addetti, territorio).
- **Generazione:** IPF/raking per ottenere distribuzioni congiunte coerenti con i marginali ISTAT; estrazione per quote dalla popolazione generata.
- **Sovracampionamento:** ammesso per segmento; i pesi di post-stratificazione riportano i risultati alla popolazione reale.
- **Versioning:** ogni tabella sorgente è salvata con data di estrazione e hash, per rendere i run confrontabili nel tempo.

### 2. Costruzione delle persone

- **Livello demografico:** dalle quote (età, sesso, area, istruzione, lavoro, reddito; per le PMI anche settore, dimensione e ruolo del rispondente).
- **Livello atteggiamenti:** valori e opinioni assegnati in modo coerente con il profilo, usando indagini pubbliche ISTAT (Aspetti della vita quotidiana) come riferimento distributivo; la European Social Survey è esclusa per licenza non commerciale.
- **Stile di risposta:** propensione all'acquiescenza, alla desiderabilità sociale, alla risposta "non so", tempo disponibile. Serve a far emergere gli effetti di modalità.
- **Narrativa:** il profilo viene reso in una breve descrizione in italiano, usata come system prompt dell'agente rispondente.

### 3. Simulazione delle modalità

| Modalità | Come viene simulata | Effetti da riprodurre |
| --- | --- | --- |
| CAWI | L'agente riceve una pagina alla volta con tutte le opzioni visibili e risponde senza interlocutore | Primacy, satisficing, straightlining sulle griglie, abbandono |
| CATI | Un agente intervistatore legge le domande; il rispondente ascolta le opzioni in sequenza e può chiedere chiarimenti | Recency, desiderabilità sociale, risposte più brevi, effetto intervistatore |
| CAPI | Come CATI, con cartellini mostrati per le scale e maggiore relazione | Desiderabilità sociale più alta, meno non risposte, effetto intervistatore |

Il questionario sorgente è unico; il sistema genera le versioni per modalità (griglie spezzate al telefono, opzioni lette, cartellini). Le versioni generate vanno riviste a mano prima del congelamento.

**Rilanci da copione**

Le tracce qualitative prevedono spesso un rilancio per domanda («Un solo rilancio»): una frase che l'intervistatore dice dopo la risposta spontanea per far emergere ciò che il rispondente non ha citato da solo. La domanda lo dichiara con `probe`. In CATI e CAPI l'intervistatore lo legge una sola volta, dopo la prima risposta e prima di ogni altro intervento; la risposta spontanea resta in `answer_text`, quella dopo il rilancio va in `probe_text`, così l'analisi può distinguere ciò che è stato citato spontaneamente. In CAWI non c'è interlocutore e il rilancio non viene applicato. Il campo `coding_note` («Cosa annoti») è un'istruzione per chi analizza: finisce nel codebook, mai nei prompt.

**Segnali non verbali**

Ogni risposta in CATI e CAPI è accompagnata da segnali non verbali simulati, per cogliere la distanza tra ciò che la persona dice e ciò che pensa davvero. Un intervistatore umano lo farebbe d'istinto: "ho provato a cambiare operatore" detto con esitazione racconta una storia diversa.

| Modalità | Segnali disponibili |
| --- | --- |
| CAWI | Nessun segnale non verbale; solo paradati di comportamento (tempi, abbandoni, risposte cambiate) |
| CATI | Paraverbali: pause, esitazioni, tono, ritmo, sospiri, risposte evasive |
| CAPI | Paraverbali più linguaggio del corpo: espressione, sguardo, postura, gesti |

Come funziona:

- **Rispondente:** oltre alla risposta verbale, l'agente produce un blocco strutturato con i segnali coerenti con il suo profilo e con il suo reale atteggiamento verso la domanda. È la "verità" simulata.
- **Intervistatore:** riceve solo i segnali percepibili nella sua modalità (al telefono niente linguaggio del corpo), li annota e può usarli per decidere un approfondimento.
- **Vocabolario fisso:** esitazione, incertezza, entusiasmo, disinteresse, irritazione, imbarazzo, ciascuno con intensità da 1 a 3, più una nota libera breve.
- **Incongruenza:** l'intervistatore segnala quando i segnali contraddicono la risposta verbale. Il report mostra le incongruenze per domanda e per segmento.
- **Configurabile:** attivabile o disattivabile da configurazione, per confrontare i risultati con e senza.

È il dato più inventato dell'intero sistema: va letto come ipotesi qualitativa da verificare, mai come misura. Per confrontarlo con le interviste reali, gli intervistatori umani dovrebbero annotare i segnali con la stessa griglia.

### 4. Disegno e repliche

- **Within-subject (default):** ogni persona risponde in tutte le modalità abilitate. Stima pulita degli effetti di modalità.
- **Between-subject:** ogni persona in una sola modalità, assegnata a caso. Serve a replicare esattamente il disegno delle interviste reali.
- **Repliche:** ogni intervista ripetuta k volte (default 3) per separare la variabilità del modello da quella del profilo.
- **Ensemble:** opzionale, più modelli LLM sulle stesse persone; la divergenza tra modelli segnala domande fragili.
- **Pilota:** prima di ogni run completo, 10-15 persone per individuare risposte piatte o incoerenti.

### 5. Congelamento e validazione ex post

Prima delle interviste reali il run viene congelato: versione del modello, prompt, parametri, seed e versioni dei dati sono salvati in un manifest con hash. Un run congelato non si modifica; ogni correzione genera un nuovo run.

Quando arrivano i dati reali, il modulo di validazione li confronta con il sottoinsieme simulato che replica lo stesso disegno. Metriche definite ora:

- Distanza tra distribuzioni per domanda (Jensen-Shannon, variazione totale).
- Correlazione tra medie o quote simulate e reali sull'insieme delle domande.
- Coerenza delle differenze tra sottogruppi (età, area, micro vs medie imprese).
- Direzione degli effetti di modalità, solo per le modalità osservate anche nel reale.
- Intervalli di confidenza sul campione reale, per non scambiare rumore per errore del modello.

Le modalità senza controparte reale vanno etichettate nell'output come stime non validate.

## Modelli dati e output

Ogni entità ha uno schema tipizzato (Pydantic) e viene serializzata in JSON o Parquet.

**Questionario (input, YAML)**

```yaml
id: mercato_v1
language: it
version: "1.0"
sections:
  - id: s1
    title: Fornitura di energia
    questions:
      - id: q1
        text: "Quanto è soddisfatto del suo attuale fornitore di energia?"
        type: scale          # single | multi | scale | grid | open | numeric
        scale: {min: 1, max: 10, labels: {1: "Per nulla", 10: "Del tutto"}}
        sensitive: false
        applies_to: [consumer, pmi]   # omesso = tutti i segmenti
        dont_know: true      # "non so" gestito per modalità (vedi sotto)
        page: 1              # pagina CAWI (facoltativo)
      - id: q2
        text: "..."
        type: single
        options: ["...", "...", "Altro"]
        randomize: true      # ordine delle opzioni casuale per intervista
        fixed_last: ["Altro"]  # voci che restano in coda
        show_if: "q1 <= 5"
      - id: q4
        type: multi
        options: ["...", "..."]
        max_choices: 3
      - id: q5
        type: grid
        items: [{id: a, text: "..."}, {id: b, text: "..."}]
        scale: {min: 1, max: 5}   # oppure options (colonne)
      - id: q6
        type: numeric
        min: 0
        max: 5000
        unit: euro
      - id: q7
        text: "Cosa le porta via più tempo nella gestione dell'attività?"
        type: open
        probe: "E l'energia, dove sta in questa lista?"   # rilancio da copione, solo CATI/CAPI
        coding_note: "Energia citata spontaneamente: sì/no"  # per l'analisi, mai letta
```

Il questionario è un **dato di input** che cambia a ogni progetto: il codice non ne conosce il contenuto e gli agenti lo leggono a runtime nella versione adattata alla modalità. `show_if` usa un linguaggio di espressioni valutato senza `eval`: confronti con risposte precedenti (`q1 <= 5`, `q2 == "Prezzo"`, `q3 in ["a", "b"]`, `q4 contains "x"` per le multiple, `q5.a >= 4` per gli item di griglia), `and`, `or`, `not`, parentesi e `answered(q)`. Una risposta assente o "non so" rende falso ogni confronto che la riguarda.

**Regole di adattamento per modalità**

| | CAWI | CATI | CAPI |
| --- | --- | --- | --- |
| Presentazione | pagine (`page`), tutte le opzioni visibili | una domanda alla volta, opzioni lette in sequenza | come CATI, cartellino per scale e liste oltre 4 opzioni |
| Griglie | intere | spezzate in una domanda per item, scala ripetuta | intere, con cartellino |
| Scale lunghe | etichette complete | letti solo gli estremi | cartellino con etichette |
| "Non so" (`dont_know`) | opzione mostrata in coda | non letto, accettato se spontaneo | non letto, accettato se spontaneo |
| Randomizzazione | per intervista, se `randomize` e `engine.randomize_option_order` | idem, sulle opzioni lette | idem |
| Domande sensibili | nessuna nota | nota all'intervistatore | nota all'intervistatore |
| Rilancio (`probe`) | non applicato (nessun interlocutore) | letto una sola volta dopo la risposta spontanea; poi l'intervistatore può solo accettare o chiarire | idem |

Le versioni generate si esportano in YAML e Markdown per la revisione manuale prima del congelamento.

**Persona**

Campi: `persona_id`, `segment`, attributi demografici, attributi impresa (per le PMI), atteggiamenti, stile di risposta, `narrative`, `source_versions`.

**Risposta (una riga per domanda)**

| Campo | Contenuto |
| --- | --- |
| run\_id, persona\_id, segment | Identificativi |
| mode, replicate, model | Modalità, numero di replica, modello usato |
| question\_id, answer\_code, answer\_text | Risposta codificata e testo libero |
| option\_order | Ordine delle opzioni presentato |
| clarification\_requested, item\_nonresponse, nonverbal\_emitted, nonverbal\_observed, incongruence | Paradati per domanda; segnali non verbali emessi dal rispondente, annotati dall'intervistatore e incongruenze |
| probe, probe\_text | Rilancio avvenuto (da copione o deciso dall'intervistatore) e risposta data dopo il rilancio |
| tokens\_in, tokens\_out, latency\_ms | Costi e tempi tecnici |

**Contenuto di ogni cartella di run**

- `manifest.json`: configurazione completa, versioni di dati, modello e prompt, hash, stato di congelamento.
- `personas.parquet` e `responses_long.parquet`.
- `responses_wide.csv` e `.sav` (una riga per persona × modalità × replica), con pesi.
- `codebook.json` (e opzionalmente DDI), `transcripts/` con i dialoghi CATI e CAPI.
- `report.html`: distribuzioni, confronto tra segmenti, effetti di modalità, stabilità tra repliche.
- `interviste.html`: pagina autonoma (un file, nessuna dipendenza esterna, funziona offline) per leggere interviste e risposte. Sempre prodotta, insieme al report, a fine run e da `survey-simulator report`. Contiene:
  - riepilogo: persone per segmento, interviste completate, risposte, risposte ai rilanci; avviso che i dati sono simulati;
  - vista **per domanda**: testo, rilancio da copione e `coding_note`; una riga per persona con la risposta in ogni modalità affiancata e, sotto, la risposta al rilancio; incongruenze segnalate;
  - vista **per persona**: profilo (`narrative`, segmento, età, regione, impresa) e le interviste delle varie modalità affiancate, domanda per domanda;
  - filtri per segmento e per replica (se più di una), ricerca nel testo con evidenziazione, opzione per mostrare i segnali non verbali emessi e il pensiero non detto (`note`).

  Non contiene `unit_id`, codici cliente né altro da `private/`: solo persone sintetiche e loro risposte. Le preferenze di vista restano nel browser (`localStorage`), mai i dati.

## Stack tecnologico e repository

Python è la scelta naturale: ecosistema statistico maturo, SDK per tutti i principali LLM, formati SPSS/Stata supportati.

| Area | Scelta proposta |
| --- | --- |
| Linguaggio e packaging | Python 3.12, uv, pyproject.toml |
| Schemi e config | Pydantic v2, YAML |
| Dati | Polars (o pandas), PyArrow per Parquet, pyreadstat per .sav/.dta |
| Campionamento | Implementazione IPF propria o libreria dedicata, numpy |
| LLM | Interfaccia astratta `LLMClient` con adapter Anthropic e OpenAI; chiamate async con limiti di concorrenza e retry |
| Cache | Cache su disco delle chiamate LLM indicizzata per hash del prompt (riproducibilità e risparmio) |
| Importazione del questionario | python-docx, pypdf, openpyxl per l'estrazione del testo; agente LLM con output vincolato a uno schema di bozza, convertito nel formato YAML |
| CLI | Typer |
| Report | Jinja2 + grafici statici (matplotlib o plotly) in HTML |
| Qualità | pytest, ruff, mypy, pre-commit, GitHub Actions |
| Licenza | Proprietaria: repository privato, nessuna licenza open source; file LICENSE con "Tutti i diritti riservati". Citare ISTAT come fonte secondo i suoi termini d'uso |

**Struttura del repository**

```
survey_simulator/
├── README.md
├── CLAUDE.md                 # istruzioni per Claude Code
├── docs/
│   ├── SPEC.md               # questo documento
│   └── methodology.md
├── configs/examples/         # config di esempio (100, 500, 1000)
├── questionnaires/examples/
├── .claude/skills/survey-simulator-run/   # skill per condurre un run da una sessione di Claude Code (M13)
├── data/
│   ├── raw/                  # estrazioni ISTAT (non versionate)
│   └── processed/            # tabelle normalizzate + manifest fonti
├── src/survey_simulator/
│   ├── config/               # schema e validazione YAML
│   ├── population/           # loader ISTAT, IPF, estrazione per quote, pesi
│   ├── personas/             # attributi, atteggiamenti, stile, narrativa
│   ├── questionnaire/        # parser, routing, adattamento per modalità
│   ├── modes/                # cawi.py, cati.py, capi.py
│   ├── agents/               # rispondente, intervistatore, prompt
│   ├── llm/                  # client astratto, adapter, cache
│   ├── runner/               # orchestrazione, repliche, congelamento, costi
│   ├── output/               # export, codebook, report
│   ├── validation/           # confronto con dati reali
│   └── cli.py
└── tests/
```

Comandi CLI previsti: `survey-simulator config validate <file>`, `survey-simulator data fetch`, `survey-simulator sample preview`, `survey-simulator run --pilot`, `survey-simulator run`, `survey-simulator freeze`, `survey-simulator report`, `survey-simulator validate --real <file>`.

## Roadmap per milestone

Ogni milestone è un blocco consegnabile e testabile, pensato per una o poche sessioni di Claude Code. Non si passa alla successiva finché i criteri di completamento non sono soddisfatti.

1. **M0 – Scheletro del progetto.** Repo, pyproject, CLI vuota, CI, CLAUDE.md, SPEC.md. *Fatto quando:* `survey-simulator --help` funziona e la CI è verde.
2. **M1 – Configurazione.** Schema Pydantic del YAML, validazione, messaggi d'errore chiari, config di esempio. *Fatto quando:* config valide e non valide sono coperte da test.
3. **M2 – Dati ISTAT.** Loader per le tabelle consumer e imprese, normalizzazione, manifest delle fonti. *Fatto quando:* le tabelle sono riproducibili da script e versionate con hash.
4. **M3 – Popolazione e campione.** IPF, estrazione per quote, sovracampionamento, pesi, controllo celle piccole, `sample preview`. *Fatto quando:* i marginali del campione rispettano le quote e i pesi ricostruiscono i marginali ISTAT.
5. **M4 – Persone.** Atteggiamenti, stile di risposta, narrativa in italiano. *Fatto quando:* 20 persone di esempio sono revisionate a mano e coerenti.
6. **M5 – Questionario.** Parser, routing con `show_if`, adattamento automatico per modalità. *Fatto quando:* un questionario reale nel formato strutturato viene caricato e le tre versioni sono esportabili per revisione.
7. **M6 – Livello LLM.** Client astratto, primo adapter, cache, retry, conteggio costi. *Fatto quando:* i test girano con un client finto, senza chiamate reali.
    - **M6b – Importazione del questionario.** Comando `survey-simulator questionnaire import <file>`: estrazione del testo da Word, PDF, Excel o testo con librerie dedicate; un agente importatore (prompt in `agents/prompts/`) produce lo YAML strutturato con output vincolato allo schema di M5, compreso il routing dedotto dalle istruzioni di salto; validazione automatica con nuovo giro dell'agente sugli errori; rapporto di importazione in Markdown con le incertezze da rivedere. La revisione umana resta obbligatoria prima del congelamento. *Fatto quando:* un questionario reale in Word o PDF produce uno YAML valido con un rapporto revisionabile.
8. **M7 – Modalità CAWI.** Agente rispondente, una pagina alla volta, randomizzazione delle opzioni. *Fatto quando:* un pilota da 10 persone produce risposte valide.
9. **M8 – Modalità CATI e CAPI.** Agente intervistatore, dialogo, cartellini, trascrizioni. *Fatto quando:* le stesse 10 persone completano entrambe le modalità.
10. **M9 – Runner.** Disegno within/between, repliche, concorrenza, stima costi, budget, congelamento. *Fatto quando:* un run da 100 × 3 modalità × 3 repliche completa e può essere congelato.
11. **M10 – Output e report.** Export long/wide, .sav, codebook, report HTML. *Fatto quando:* il dataset si apre in SPSS/R e il report mostra segmenti ed effetti di modalità. Aggiunta dell'8 novembre 2026: la pagina `interviste.html` per leggere interviste e risposte, prodotta sempre accanto al report.
12. **M11 – Validazione.** Import dati reali, allineamento al disegno, metriche, report di confronto. *Fatto quando:* testato su un dataset reale di prova (anche fittizio).
13. **M12 – Ensemble e rifinitura.** Secondo provider LLM, documentazione, esempi, release v0.1 su GitHub.
14. **M13 – Anagrafiche e avvio da Claude Code.** Sorgente `lista_clienti`: il campione è l'anagrafica del committente (CSV o Excel con intestazioni variabili), ISTAT completa gli attributi mancanti; comando `survey-simulator prepare` che da questionario e anagrafica scrive la configurazione e stima il run; skill di progetto per guidare la sessione di Claude Code. *Fatto quando:* `prepare` su un'anagrafica reale produce una configurazione valida con il rapporto dei record scartati, `run --pilot` parte, e nessun dato personale del file (nomi, codici fiscali, contatti) compare nei prompt o negli output condivisibili.
15. **M14 – Provider sessione.** Adapter `session` con cassetta delle richieste su file, comandi `session list` e `session answer`, sospensione e ripresa dei run. *Fatto quando:* un pilota CAWI da 10 persone viene completato rispondendo dalla sessione di Claude Code e produce output validi.

## Lavorare con Claude Code

Il modo più efficace è salvare questo documento come `docs/SPEC.md` nel repo e creare un `CLAUDE.md` breve alla radice, che Claude Code legge a ogni sessione. Poi si procede una milestone alla volta.

**Contenuto suggerito per CLAUDE.md**

```markdown
# survey_simulator

Simulatore di indagini su popolazione sintetica italiana.
Specifica completa: docs/SPEC.md. Leggila prima di ogni milestone.

## Regole
- Lavora una milestone alla volta (vedi Roadmap in SPEC.md).
  Prima di scrivere codice, proponi un piano e aspetta conferma.
- Nessun parametro di campione o di questionario nel codice: tutto da config.
- Ogni modulo ha test; nei test usa sempre il client LLM finto,
  mai chiamate reali.
- Riproducibilità: ogni casualità passa dal seed della config.
- Un run congelato non si modifica mai.
- Prompt degli agenti in file separati (src/survey_simulator/agents/prompts/),
  in italiano, versionati.
- Chiavi API solo da variabili d'ambiente (.env non versionato).

## Comandi
- uv run pytest
- uv run ruff check . && uv run mypy src
- uv run survey-simulator --help
- uv run survey-simulator questionnaire import <file> --config <config> --out <yaml>
- uv run survey-simulator interview preview --config <config> --mode cawi --n 10 --out <dir>
- uv run survey-simulator run --config <config> [--pilot] [--estimate-only] [--run-id <nome>]
- uv run survey-simulator freeze <cartella del run> [--verify]
- uv run survey-simulator report <cartella del run> [--out <cartella>] [--formats parquet,csv,sav]
- uv run survey-simulator validate <cartella del run> --real <csv> [--out <cartella>]
- uv run survey-simulator prepare --questionnaire <file> --contacts <file> --out <cartella>
- uv run survey-simulator session list --config <config>  /  session answer <risposte.json> --config <config>
```

**Come impostare ogni sessione**

- Apri con un prompt del tipo: "Leggi docs/SPEC.md e implementa la milestone M3. Prima proponi il piano."
- Rivedi il piano, poi lascia implementare. Chiudi la sessione quando i criteri di completamento sono soddisfatti e la CI è verde.
- Fai un commit (o una pull request) per milestone, così ogni passo è reversibile.
- Se una scelta cambia durante il lavoro, aggiorna prima SPEC.md e poi il codice: il documento resta la fonte di verità.

## Rischi e questioni aperte

| Rischio | Impatto | Mitigazione |
| --- | --- | --- |
| Risposte LLM troppo omogenee | Varianza sottostimata, conclusioni troppo nette | Persone ricche di atteggiamenti, temperatura > 0, repliche, ensemble |
| Bias del modello (opinioni istruite, urbane) | Distorsione sistematica su alcuni segmenti | Confronto tra modelli, validazione ex post, calibrazione futura |
| Effetti di modalità non realistici | Stime di modalità fuorvianti | Pilota, revisione delle trascrizioni, confronto con letteratura |
| Celle piccole con n basso | Profili poco rappresentativi | Avvisi e accorpamento automatico in fase di config |
| Costi LLM con n alto | Run da 1.000 × 3 modalità × 3 repliche costosi | Stima preventiva, budget massimo, cache |
| Uso improprio dei risultati | Simulato scambiato per dato reale | Etichette chiare nell'output e nel report |

**Decisioni prese**

- Il sistema simula sempre tutte e tre le modalità (CAWI, CATI, CAPI), indipendentemente dal disegno delle interviste reali.
- Provider e modelli LLM: si parte confrontandone alcuni nel pilota, poi si affina la scelta con i casi reali. L'architettura multi-provider resta obbligatoria.
- Modalità operativa (8 novembre 2026): nessun credito API; il modello è la sessione di Claude Code tramite il provider `session` (M14). Gli adapter Anthropic e OpenAI restano nel codice e nei test per un eventuale ritorno alle API.
- Motore ibrido: rinviato a dopo la raccolta dei dati reali.
- Interfaccia v1: solo riga di comando.
- Distribuzione: prodotto proprietario in repository privato, per uso commerciale.
- Dati ISTAT (M2): solo aggregati pubblici via API SDMX, niente microdati. Popolazione al 1° gennaio 2025, Censimento permanente al 31 dicembre 2024 per istruzione e condizione professionale, ASIA 2024 in ATECO 2007. Il reddito non è una variabile di quota: viene assegnato alla persona in M4. Le tavole normalizzate sono versionate in git con manifest e hash; i file grezzi no.
- Popolazione sintetica (M3): congiunta degli individui su regione × sesso × gruppo d'età quinquennale × istruzione × condizione via IPF, vincoli dal censimento e marginale esatto dalla popolazione residente, Forze di lavoro come seed (gradiente per età e associazione istruzione-condizione). Con sovracampionamento i target delle altre quote vengono dalla popolazione di disegno; i pesi riportano alla popolazione reale e dichiarano le variabili non ricostruibili. `allocation: proportional` usa le popolazioni filtrate.
- Popolazione sintetica, correzione dopo la revisione di M4 (8 novembre 2026): il seed dell'IPF esclude occupati e persone in cerca di lavoro da 80 anni in su (`individui.NO_WORK_AGE`), così la quota censuaria dei 65+ si concentra fra i 65 e i 79 anni e non compaiono ottantenni al lavoro.
- Questionario (M5): il questionario cambia a ogni progetto ed è un dato di input, mai nel codice; il formato YAML strutturato è il contratto per routing, randomizzazione, codebook e dataset. L'importazione del questionario grezzo (Word, PDF, Excel) fa parte del prodotto con un agente LLM e revisione umana obbligatoria (milestone M6b).
- Importazione del questionario (M6b): il modello non scrive direttamente lo YAML di M5 ma una bozza con schema JSON adatto all'output strutturato (tutti i campi espliciti, etichette di scala come lista di coppie, nessun vincolo numerico o di pattern); la bozza è convertita e validata con il parser di M5 e gli errori tornano al modello per al massimo due giri di correzione. L'import usa `effort: high` e 16.000 token di uscita di default, indipendenti dall'`engine` delle interviste. Una bozza ancora non valida viene salvata come `.draft.yaml` con il rapporto degli errori. Niente OCR: un PDF scansionato viene rifiutato.
- Interviste CAWI (M7): una chiamata per pagina con schema JSON che elenca le domande visibili; le pagine precedenti restano nella conversazione per la coerenza. Le domande di una pagina che dipendono da altre della stessa pagina sono presentate in un gruppo successivo. Il rispondente può abbandonare (`abandon`) e le domande non raggiunte restano con stato `abandoned`; le domande saltate dal routing o dal segmento hanno stato `not_applicable`. Le risposte fuori schema (valori non ammessi, numeri fuori limite) diventano non risposta con `item_nonresponse`. Il codice di risposta è l'indice nell'ordine canonico delle opzioni, l'ordine presentato è registrato in `option_order`. Il generatore dell'intervista deriva da `SeedSequence([seed, 7, indice persona, modalità, replica])`.
- Interviste CATI e CAPI (M8): per ogni domanda una chiamata al rispondente, che restituisce battuta a voce, risposta codificata, eventuale richiesta di chiarimento e blocco dei segnali non verbali (sei segnali con intensità 0-3, linguaggio del corpo, nota). L'agente intervistatore (prompt `interviewer_it.j2`) viene chiamato solo se serve: chiarimento chiesto, risposta non codificabile o segnale osservato di intensità almeno 2; può accettare, chiarire o approfondire una volta, e annota l'incongruenza fra segnali e parole. Al telefono l'intervistatore osserva solo i segnali paraverbali, di persona anche il corpo; il blocco emesso resta registrato per intero come "verità" simulata. Il contesto del rispondente conserva gli ultimi otto scambi. Non è previsto l'abbandono nelle interviste con intervistatore.
- Runner (M9): la cartella del run è `<output.dir>/<run_id>` con `run_id` di default `<progetto>-<data e ora UTC>[-pilota]`. La stima di costo è prudente (prezzo pieno, senza cache, contesto crescente) e blocca il run prima di qualsiasi chiamata se supera `run.budget_max_eur`; durante il run la spesa reale viene confrontata con il budget prima di ogni intervista e, se lo supera, le interviste non iniziate vengono saltate con stato `budget_exceeded`. Nel disegno between-subject l'assegnazione alle modalità usa i resti più grandi e il ramo 9 del seed. `run.frozen: true` congela la cartella alla fine del run; `survey-simulator freeze` la congela dopo e `--verify` ne controlla gli hash. Un run congelato non può essere riscritto con lo stesso `run_id`. La cache delle risposte rende riavviabile un run interrotto senza pagare due volte.
- Output (M10): il dataset largo ha una riga per persona × modalità × replica × modello; singole come codice 1..k nell'ordine canonico, multiple come variabili 0/1 per opzione (`<id>_<n>`), griglie come `<id>_<item>`, aperte come testo con `<id>_status`; mancanti con codici negativi (-1 non applicabile, -2 non risposta, -3 non so, -4 abbandono) dichiarati come missing nel .sav. Il report HTML usa grafici SVG inline (nessuna libreria grafica), etichetta ogni pagina come SIMULATA e include esito per modalità, distribuzioni pesate, effetti di modalità rispetto al CAWI, confronto fra segmenti, stabilità fra repliche, straightlining nelle griglie, incongruenze non verbali e costi. `survey-simulator run` produce già tutti gli output; `survey-simulator report` li rigenera e, per un run congelato, richiede `--out` verso un'altra cartella.
- Validazione (M11): i dati reali arrivano in CSV lungo (`respondent_id`, `mode`, `question_id`, `answer_code`, facoltativi `item_id`, `segment`, `weight`; stesse convenzioni di codifica del dataset lungo simulato, righe assenti = non applicabile) o largo (variabili con i nomi del dataset largo simulato). Il confronto usa solo le modalità presenti in entrambi; le altre sono etichettate come non validate. Metriche: Jensen-Shannon in base 2 e variazione totale per variabile codificata, media o quota della risposta prevalente con intervallo di confidenza al 95% calcolato sul campione reale (normale), correlazione di Pearson fra valori simulati e reali (quote e medie separate), accordo di segno e correlazione delle differenze fra sottogruppi (segmento, classe d'età, area, sesso, dimensione, istruzione, dove presenti in entrambi) e fra modalità. Il rapporto è in Markdown e JSON, in `<run>/validation/` o in `--out` se il run è congelato.
- Secondo provider ed ensemble (M12): l'adapter OpenAI usa Chat Completions con `response_format` `json_schema` in modalità `strict` (stessi schemi dell'adapter Anthropic: tutti i campi obbligatori, `additionalProperties: false`), `reasoning_effort` per i modelli che ragionano (serie `o` e `gpt-5`) e `temperature` solo per gli altri e solo se indicata; la chiave arriva da `OPENAI_API_KEY`. I token letti dalla cache automatica di OpenAI sono scalati dai token in ingresso e prezzati a parte. Con più modelli in `engine.models` il runner esegue l'intero piano per ciascuno e il report aggiunge la sezione ensemble: per ogni variabile il valore per modello e la divergenza (massimo meno minimo), ordinata dalla più alta, come indicatore delle domande fragili. Qualunque modello del provider `fake` ha prezzo zero.
- Anagrafiche (M13): il file del committente non è mai uguale, quindi le colonne vengono riconosciute da sinonimi italiani e inglesi (sesso, età o data di nascita, codice fiscale, regione, provincia, codice ISTAT del comune, CAP, partita IVA, ragione sociale, codice ATECO, addetti, ruolo, tipologia cliente) con una mappatura esplicita in configurazione quando serve. Età e sesso, se assenti, si ricavano dal codice fiscale, che poi viene scartato; la regione dalla provincia (sigla o nome) o dalle prime tre cifre del codice ISTAT del comune, tramite la tabella `population/province_it.yaml`. L'unità (individuo o impresa) viene dalla colonna di tipologia cliente se c'è, altrimenti dalla presenza della partita IVA; un'impresa con codice fiscale di persona ha il rispondente già noto per sesso ed età. I record vengono deduplicati per codice cliente, codice fiscale o partita IVA. Istruzione, condizione professionale, reddito e atteggiamenti vengono dalle distribuzioni ISTAT condizionate a regione, sesso ed età; il settore dal codice ATECO (divisione), la classe dimensionale dagli addetti o, se assenti, dalla distribuzione ASIA per regione e settore. La provenienza `anagrafica` si aggiunge a campione, ISTAT e ipotesi. I pesi valgono 1: l'anagrafica è l'universo. **Privacy**: nomi, codici fiscali, indirizzi e contatti non entrano mai nel campione, nei prompt o negli output; le persone usano nomi sintetici; la corrispondenza persona-record sta in `<run>/private/contacts_map.csv`, da non condividere.
- Provider `session` (M14): per piloti senza credito API il modello è la sessione di Claude Code. L'adapter non chiama nessuna API: scrive ogni richiesta senza risposta in `<cache_dir>/session/pending/<impronta>.json` (system, messaggi, schema, metadati) e solleva `AwaitingAnswersError`; il runner e `interview preview` sospendono le interviste in attesa, registrano lo stato `paused` e indicano quante richieste aspettano. Le risposte si depositano con `survey-simulator session answer <file json>` (impronta -> oggetto conforme allo schema, validato) in `session/answers/`; al rilancio dello stesso comando le interviste riprendono dal passo successivo. Ogni passo sequenziale (pagina CAWI, domanda CATI/CAPI) richiede un giro. Il modello si chiama `session` e ha prezzo zero; i record riportano `model = session`. È uno strumento per decine di interviste, non per i run completi: niente concorrenza reale, niente prompt caching, e la qualità dipende da chi risponde nella sessione.
- Rilanci da copione (8 novembre 2026): il questionario reale del caso di riferimento è una traccia qualitativa con un rilancio e una nota di codifica per domanda. La domanda ha due campi facoltativi: `probe`, letto dall'intervistatore una sola volta dopo la risposta spontanea in CATI e CAPI (non in CAWI, non sulle griglie), e `coding_note`, istruzione per l'analisi riportata nel codebook. Il record ha `probe_text` con la risposta dopo il rilancio; `answer_text` resta la risposta spontanea. Dopo un rilancio da copione l'agente intervistatore non approfondisce più: accetta o chiarisce.
- Persone (M4): la European Social Survey è CC BY-NC-SA (solo uso non commerciale) e non viene usata; atteggiamenti da Aspetti della vita quotidiana, reddito da EU-SILC aggregata, imprese dal Censimento permanente delle imprese, tutti ISTAT. I tratti senza fonte (prezzo, marca, rischio, novità) e lo stile di risposta sono priori dichiarati in YAML, sostituibili da config, marcati "ipotesi" in persona, narrativa e codebook. Nomi di battesimo da lista curata, disattivabili (`personas.include_names`).

**Questioni aperte**

- ~~Uso commerciale dei dati ISTAT all'interno di un prodotto proprietario~~ Risolta in M2: i dati aggregati ISTAT sono rilasciati con licenza CC BY 3.0 IT, che ammette l'uso commerciale con citazione della fonte (vedi docs/methodology.md, sezione 1). Restano da verificare le condizioni d'uso della European Social Survey prima di M4.
