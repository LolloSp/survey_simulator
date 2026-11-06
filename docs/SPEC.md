# Simulatore di indagini su popolazione sintetica italiana — Specifica di progetto

Nov 5, 2026 · @Lorenzo Spanu

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

personas:
  priors_path: null            # YAML con i priori dei tratti senza fonte ISTAT (default nel pacchetto)
  include_names: true          # nome di battesimo nella narrativa

modes:
  design: within_subject       # within_subject | between_subject
  enabled: [cawi, cati, capi]
  allocation: {cawi: 0.34, cati: 0.33, capi: 0.33}   # solo between_subject

engine:
  models:                      # piu modelli = ensemble
    - provider: anthropic
      model: <da definire>
  temperature: 0.8
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
sections:
  - id: s1
    questions:
      - id: q1
        text: "Quanto è soddisfatto del suo attuale fornitore di energia?"
        type: scale          # single | multi | scale | grid | open | numeric
        scale: {min: 1, max: 10, labels: {1: "Per nulla", 10: "Del tutto"}}
        sensitive: false
        applies_to: [consumer, pmi]
      - id: q2
        text: "..."
        type: single
        options: ["...", "...", "Non so"]
        show_if: "q1 <= 5"
```

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
| tokens\_in, tokens\_out, latency\_ms | Costi e tempi tecnici |

**Contenuto di ogni cartella di run**

- `manifest.json`: configurazione completa, versioni di dati, modello e prompt, hash, stato di congelamento.
- `personas.parquet` e `responses_long.parquet`.
- `responses_wide.csv` e `.sav` (una riga per persona × modalità × replica), con pesi.
- `codebook.json` (e opzionalmente DDI), `transcripts/` con i dialoghi CATI e CAPI.
- `report.html`: distribuzioni, confronto tra segmenti, effetti di modalità, stabilità tra repliche.

## Stack tecnologico e repository

Python è la scelta naturale: ecosistema statistico maturo, SDK per tutti i principali LLM, formati SPSS/Stata supportati.

| Area | Scelta proposta |
| --- | --- |
| Linguaggio e packaging | Python 3.12, uv, pyproject.toml |
| Schemi e config | Pydantic v2, YAML |
| Dati | Polars (o pandas), PyArrow per Parquet, pyreadstat per .sav/.dta |
| Campionamento | Implementazione IPF propria o libreria dedicata, numpy |
| LLM | Interfaccia astratta `LLMClient` con adapter per provider; chiamate async con limiti di concorrenza e retry |
| Cache | Cache su disco delle chiamate LLM indicizzata per hash del prompt (riproducibilità e risparmio) |
| CLI | Typer |
| Report | Jinja2 + grafici statici (matplotlib o plotly) in HTML |
| Qualità | pytest, ruff, mypy, pre-commit, GitHub Actions |
| Licenza | Proprietaria: repository privato, nessuna licenza open source; file LICENSE con "Tutti i diritti riservati". Citare ISTAT come fonte secondo i suoi termini d'uso |

**Struttura del repository**

```
synthsurvey/
├── README.md
├── CLAUDE.md                 # istruzioni per Claude Code
├── docs/
│   ├── SPEC.md               # questo documento
│   └── methodology.md
├── configs/examples/         # config di esempio (100, 500, 1000)
├── questionnaires/examples/
├── data/
│   ├── raw/                  # estrazioni ISTAT (non versionate)
│   └── processed/            # tabelle normalizzate + manifest fonti
├── src/synthsurvey/
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

Comandi CLI previsti: `synthsurvey config validate <file>`, `synthsurvey data fetch`, `synthsurvey sample preview`, `synthsurvey run --pilot`, `synthsurvey run`, `synthsurvey freeze`, `synthsurvey report`, `synthsurvey validate --real <file>`.

## Roadmap per milestone

Ogni milestone è un blocco consegnabile e testabile, pensato per una o poche sessioni di Claude Code. Non si passa alla successiva finché i criteri di completamento non sono soddisfatti.

1. **M0 – Scheletro del progetto.** Repo, pyproject, CLI vuota, CI, CLAUDE.md, SPEC.md. *Fatto quando:* `synthsurvey --help` funziona e la CI è verde.
2. **M1 – Configurazione.** Schema Pydantic del YAML, validazione, messaggi d'errore chiari, config di esempio. *Fatto quando:* config valide e non valide sono coperte da test.
3. **M2 – Dati ISTAT.** Loader per le tabelle consumer e imprese, normalizzazione, manifest delle fonti. *Fatto quando:* le tabelle sono riproducibili da script e versionate con hash.
4. **M3 – Popolazione e campione.** IPF, estrazione per quote, sovracampionamento, pesi, controllo celle piccole, `sample preview`. *Fatto quando:* i marginali del campione rispettano le quote e i pesi ricostruiscono i marginali ISTAT.
5. **M4 – Persone.** Atteggiamenti, stile di risposta, narrativa in italiano. *Fatto quando:* 20 persone di esempio sono revisionate a mano e coerenti.
6. **M5 – Questionario.** Parser, routing con `show_if`, adattamento automatico per modalità. *Fatto quando:* il questionario reale viene caricato e le tre versioni sono esportabili per revisione.
7. **M6 – Livello LLM.** Client astratto, primo adapter, cache, retry, conteggio costi. *Fatto quando:* i test girano con un client finto, senza chiamate reali.
8. **M7 – Modalità CAWI.** Agente rispondente, una pagina alla volta, randomizzazione delle opzioni. *Fatto quando:* un pilota da 10 persone produce risposte valide.
9. **M8 – Modalità CATI e CAPI.** Agente intervistatore, dialogo, cartellini, trascrizioni. *Fatto quando:* le stesse 10 persone completano entrambe le modalità.
10. **M9 – Runner.** Disegno within/between, repliche, concorrenza, stima costi, budget, congelamento. *Fatto quando:* un run da 100 × 3 modalità × 3 repliche completa e può essere congelato.
11. **M10 – Output e report.** Export long/wide, .sav, codebook, report HTML. *Fatto quando:* il dataset si apre in SPSS/R e il report mostra segmenti ed effetti di modalità.
12. **M11 – Validazione.** Import dati reali, allineamento al disegno, metriche, report di confronto. *Fatto quando:* testato su un dataset reale di prova (anche fittizio).
13. **M12 – Ensemble e rifinitura.** Secondo provider LLM, documentazione, esempi, release v0.1 su GitHub.

## Lavorare con Claude Code

Il modo più efficace è salvare questo documento come `docs/SPEC.md` nel repo e creare un `CLAUDE.md` breve alla radice, che Claude Code legge a ogni sessione. Poi si procede una milestone alla volta.

**Contenuto suggerito per CLAUDE.md**

```markdown
# synthsurvey

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
- Prompt degli agenti in file separati (src/synthsurvey/agents/prompts/),
  in italiano, versionati.
- Chiavi API solo da variabili d'ambiente (.env non versionato).

## Comandi
- uv run pytest
- uv run ruff check . && uv run mypy src
- uv run synthsurvey --help
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
- Motore ibrido: rinviato a dopo la raccolta dei dati reali.
- Interfaccia v1: solo riga di comando.
- Distribuzione: prodotto proprietario in repository privato, per uso commerciale.
- Dati ISTAT (M2): solo aggregati pubblici via API SDMX, niente microdati. Popolazione al 1° gennaio 2025, Censimento permanente al 31 dicembre 2024 per istruzione e condizione professionale, ASIA 2024 in ATECO 2007. Il reddito non è una variabile di quota: viene assegnato alla persona in M4. Le tavole normalizzate sono versionate in git con manifest e hash; i file grezzi no.
- Popolazione sintetica (M3): congiunta degli individui su regione × sesso × gruppo d'età quinquennale × istruzione × condizione via IPF, vincoli dal censimento e marginale esatto dalla popolazione residente, Forze di lavoro come seed (gradiente per età e associazione istruzione-condizione). Con sovracampionamento i target delle altre quote vengono dalla popolazione di disegno; i pesi riportano alla popolazione reale e dichiarano le variabili non ricostruibili. `allocation: proportional` usa le popolazioni filtrate.
- Persone (M4): la European Social Survey è CC BY-NC-SA (solo uso non commerciale) e non viene usata; atteggiamenti da Aspetti della vita quotidiana, reddito da EU-SILC aggregata, imprese dal Censimento permanente delle imprese, tutti ISTAT. I tratti senza fonte (prezzo, marca, rischio, novità) e lo stile di risposta sono priori dichiarati in YAML, sostituibili da config, marcati "ipotesi" in persona, narrativa e codebook. Nomi di battesimo da lista curata, disattivabili (`personas.include_names`).

**Questioni aperte**

- ~~Uso commerciale dei dati ISTAT all'interno di un prodotto proprietario~~ Risolta in M2: i dati aggregati ISTAT sono rilasciati con licenza CC BY 3.0 IT, che ammette l'uso commerciale con citazione della fonte (vedi docs/methodology.md, sezione 1). Restano da verificare le condizioni d'uso della European Social Survey prima di M4.
