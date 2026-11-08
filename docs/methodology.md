# Metodologia

Documento in costruzione: ogni sezione viene scritta nella milestone che la
implementa (vedi Roadmap in [SPEC.md](SPEC.md)).

1. Fonti ISTAT e versionamento delle tabelle (M2): sotto
2. Generazione della popolazione: IPF/raking, quote, pesi (M3)
3. Costruzione delle persone: atteggiamenti, stile di risposta, narrativa (M4)
4. Adattamento del questionario per modalità (M5)
5. Livello LLM: client, cache, costi (M6): sotto
6. Simulazione delle modalità ed effetti attesi dalla letteratura (M7, M8): sotto
7. Segnali non verbali: vocabolario e limiti interpretativi (M8): in 6
8. Disegno, repliche, ensemble, congelamento (M9): in 7
9. Output, codebook e report (M10): in 8
10. Metriche di validazione ex post (M11): in 9
11. Anagrafiche come campione (M13): in 10

## 1. Fonti ISTAT e versionamento delle tabelle

### Accesso ai dati

Tutte le tavole vengono estratte dall'API SDMX REST di ISTAT
(`https://esploradati.istat.it/SDMXWS/rest`, agenzia `IT1`) in formato CSV
SDMX. Il client (`synthsurvey.population.istat.sdmx`) salva ogni risposta
grezza in `data/raw/<dataflow>/<hash-url>.csv` con un file di metadati
accanto: la stessa richiesta non torna in rete e in modalità offline si usa
solo la cache. I file grezzi non sono versionati; le tavole normalizzate in
`data/processed/` sì, insieme a `manifest.json` che registra per ogni tavola
dataflow, chiave, URL, periodo, data di estrazione e hash SHA-256 del grezzo e
del normalizzato. `synthsurvey data status` ricalcola gli hash.

Lo script `scripts/istat_explore.py` serve a cercare dataflow, leggere
dimensioni e codelist e sondare i dati: è lo strumento con cui sono stati
scelti i dataflow qui sotto e con cui si aggiungono sorgenti nuove.

### Tavole e periodi di riferimento

| Tavola | Fonte ISTAT (dataflow) | Periodo | Dettaglio |
| --- | --- | --- | --- |
| `population_region_sex_age` | Popolazione residente al 1° gennaio (`22_289_DF_DCIS_POPRES1_1`) | 1° gennaio 2025 | regione × sesso × età singola 0-100+ |
| `education_region_sex_ageclass` | Censimento permanente, istruzione (`DF_DCSS_ISTR_LAV_PEN_2_TV_1`) | 31 dicembre 2024 | regione × sesso × classe d'età (9-24, 25-49, 50-64, 65+) × titolo di studio |
| `employment_region_sex_ageclass` | Censimento permanente, condizione professionale (`DF_DCSS_ISTR_LAV_PEN_2_TV_3`) | 31 dicembre 2024 | regione × sesso × classe d'età (15-24, 25-49, 50-64, 65+) × condizione |
| `education_sex_ageclass_national` | Rilevazione sulle forze di lavoro, forze di lavoro + inattivi (`150_908_DF_DCCV_FORZLV1_2`, `152_928_DF_DCCV_INATTIV1_2`) | media 2024 | Italia × sesso × classe d'età decennale × titolo di studio |
| `employed_sex_ageclass_education_national` | Rilevazione sulle forze di lavoro, occupati (`150_938_DF_DCCV_OCCUPATIT1_2`) | media 2024 | Italia × sesso × classe d'età decennale × titolo di studio |
| `firms_region_sector_size` | Registro ASIA imprese attive (`183_277_DF_DICA_ASIAUE1P_5`) | 2024 | regione × settore × classe di addetti |

Le date sono coerenti fra loro: popolazione al 1° gennaio 2025, censimento al
31 dicembre 2024, ASIA 2024. I periodi sono fissati in
`synthsurvey.population.istat.tables`; cambiarli e rilanciare `data fetch`
produce un nuovo manifest.

### Mappature dei codici

- **Regioni**: codici NUTS2 della codelist `CL_ITTER107`; Trentino-Alto Adige è
  `ITDA` (somma delle due province autonome). Macro-aree: nord-ovest, nord-est,
  centro, sud, isole.
- **Titolo di studio** (3 livelli): `fino_media` = nessun titolo, licenza
  elementare, licenza media; `diploma` = diploma di scuola secondaria di II
  grado o qualifica professionale; `laurea_o_oltre` = ITS, terziario di I e II
  livello, dottorato. Nelle Forze di lavoro i codici aggregati sono 13, 7, 11.
- **Condizione professionale** (4 categorie, dal censimento): `occupato`,
  `in_cerca`, `pensionato` (percettore di pensione da lavoro),
  `altro_inattivo` (studenti, casalinghe, altra condizione).
- **Settore** (ATECO 2007, divisioni a due cifre accorpate): `industria` 05-39,
  `costruzioni` 41-43, `commercio` 45-47, `trasporti_turismo` 49-56,
  `servizi_imprese` 58-82, `altri_servizi` 85-96. Esclusi agricoltura (A),
  pubblica amministrazione (O), famiglie (T) e organismi extraterritoriali (U),
  come nel campo di osservazione ASIA. ISTAT è passata ad ATECO 2025 nel 2025;
  il registro ASIA via SDMX è ancora in ATECO 2007 e il progetto segue questa
  classificazione.
- **Classe di addetti**: `micro` 0-9 addetti (ISTAT include le imprese con 0
  addetti medi annui), `piccola` 10-49, `media` 50-249, `grande` 250+. Le PMI
  usano le prime tre; `grande` resta disponibile per una futura sorgente.

### Tavole per le persone (M4)

Per atteggiamenti, reddito e caratteristiche delle imprese il registro
comprende altre dieci tavole, tutte nazionali salvo dove indicato:

| Tavola | Fonte ISTAT (dataflow) | Periodo | Dettaglio |
| --- | --- | --- | --- |
| `trust_sex_ageclass_education` | Aspetti della vita quotidiana (`83_63_DF_DCCV_AVQ_PERSONE_124`) | 2024 | sesso x classe d'età (14-24, 25-44, 45-64, 65+) x titolo x fiducia negli altri |
| `life_satisfaction_sex_ageclass_education` | AVQ (`..._138`) | 2024 | idem x punteggio 0-10 |
| `internet_sex_ageclass_education` | AVQ (`..._236`) | 2024 | idem (6-24) x quotidiano, occasionale, mai |
| `political_info_sex_ageclass_education` | AVQ (`..._109`) | 2024 | idem x quotidiana, settimanale, saltuaria, mai |
| `religion_sex_ageclass_education` | AVQ (`..._134`, totale da `..._236`) | 2024 | idem (6-24) x settimanale, saltuaria (residuo), mai |
| `economic_judgement_region` | AVQ famiglie (`82_87_DF_DCCV_AVQ_FAMIGLIE_14`) | 2024 | regione x giudizio sulle risorse economiche |
| `income_quintile_main_earner` | EU-SILC (`32_38_DF_DCCV_QUINTOREDD_5`) | 2024 | quintile di reddito equivalente per titolo e per condizione del principale percettore |
| `income_quintile_region` | EU-SILC (`32_38_DF_DCCV_QUINTOREDD_6`) | 2024 | quintile per regione (Trentino-Alto Adige = media delle due province) |
| `firm_relations_sector_size` | Censimento permanente imprese (`742_1106_DF_DCSI_CPI_RELAZIONI_6`) | 2022 | settore x classe (3-9, 10-49, 50-249) x imprese con relazioni |
| `firm_objectives_sector_size` | Censimento permanente imprese (`742_1102_DF_DCSI_CPI_CONTROLLO_22`) | 2022 | settore x classe (10-49, 50-249) x obiettivi strategici perseguiti |

Le tavole AVQ usano i valori assoluti (migliaia di persone) così i livelli di
istruzione ISTAT 3 e 4 si sommano in `fino_media`; le classi d'età 14-24 e
6-24 includono minorenni e vengono usate per i 18-24enni come approssimazione.
Il censimento delle imprese copre solo le imprese con 3 e più addetti e gli
obiettivi strategici solo quelle con 10 e più: per le microimprese valgono
come proxy, dichiarata nella provenienza degli attributi.

### Controlli di coerenza

Ogni normalizzazione verifica che la somma delle categorie coincida con il
totale ISTAT della stessa cella (tolleranza 0,5%) e che tutte le venti regioni
siano presenti; in caso contrario l'estrazione fallisce invece di produrre
una tavola parziale.

### Limiti noti

- Le classi d'età del censimento (9-24, 25-49, 50-64, 65+) non coincidono con
  le fasce delle persone (18-24, 25-34, ...). La tavola nazionale delle Forze
  di lavoro, per classi decennali, serve a ripartire le classi larghe in M3.
- La classe 9-24 della tavola istruzione include minorenni; per la fascia 18-24
  la distribuzione del titolo di studio va presa dalla tavola nazionale 15-24.
- I valori delle Forze di lavoro sono stime campionarie in migliaia; il
  censimento permanente è anch'esso basato su rilevazione campionaria
  integrata con registri, con stime arrotondate. Le somme fra tavole diverse
  non tornano al singolo individuo.

### Licenza e citazione

I dati aggregati ISTAT sono pubblicati con licenza Creative Commons
Attribuzione 3.0 Italia, che ammette riproduzione, distribuzione e
adattamento anche a fini commerciali citando la fonte. Il manifest riporta la
dicitura da usare: "Fonte: ISTAT (www.istat.it), elaborazione synthsurvey".

## 2. Generazione della popolazione: IPF, quote, pesi

### Individui

La popolazione sintetica degli individui maggiorenni è una distribuzione
congiunta su cinque assi: regione (20) × sesso (2) × gruppo d'età
quinquennale (14: 18-24, 25-29, ..., 85+) × titolo di studio (3) ×
condizione professionale (4), 6.720 celle. Il gruppo quinquennale è la
risoluzione interna perché si ricompone esattamente nelle classi del
censimento (25-49, 50-64, 65+) e in quelle decennali delle Forze di lavoro;
la fascia d'età delle persone (18-24, 25-34, ...) e l'età puntuale si
ricavano dopo.

La congiunta è stimata con iterative proportional fitting
(`synthsurvey.population.ipf`) con tre vincoli:

1. regione × sesso × gruppo quinquennale: marginale assoluto dalla
   popolazione residente al 1° gennaio 2025, applicato per ultimo a ogni
   iterazione, quindi esatto;
2. quote di titolo di studio per regione × sesso × classe censuaria (18-24,
   25-49, 50-64, 65+), dal Censimento permanente;
3. quote di condizione professionale sulle stesse celle, dal censimento.

I vincoli 2 e 3 sono condizionali: a ogni iterazione il target assoluto è
ricalcolato dalla massa corrente della cella, così i totali del censimento
(31 dicembre 2024, stime arrotondate) non entrano in conflitto con la
popolazione residente. Essendo condizionati alle stesse celle, i tre vincoli
sono sempre compatibili e l'IPF converge in meno di dieci iterazioni.

Le Forze di lavoro non sono un vincolo ma il **seed** dell'IPF: il seed porta
il gradiente del titolo di studio per classe decennale (dentro la classe
censuaria 25-49 i 25-29enni sono più laureati dei 45-49enni) e
l'associazione fra istruzione e condizione (quota di occupati per sesso,
classe decennale e titolo, dalla tavola degli occupati). L'IPF conserva le
interazioni del seed dove i vincoli non le fissano; i livelli restano quelli
del censimento. Questa scelta evita il conflitto fra le due fonti, che
stimano livelli diversi di istruzione (9,3 contro 8,6 milioni di laureati).

Due correzioni sui minorenni: la classe censuaria 9-24 (istruzione) e 15-24
(condizione) include ragazzi che non possono avere un diploma ed sono quasi
tutti studenti. I 9-17enni e i 15-17enni, presi dalla popolazione residente
per regione e sesso, vengono sottratti rispettivamente da `fino_media` e da
`altro_inattivo` prima di calcolare le quote, che diventano così quote dei
18-24enni.

Dopo la revisione delle persone di M4 il seed esclude occupati e persone
in cerca di lavoro dagli 80 anni in su: le celle a zero restano a zero
nell'IPF e la quota censuaria dei 65+ si distribuisce fra i 65 e i 79 anni.

### Imprese

La tavola ASIA è già una congiunta esatta regione × settore × classe di
addetti: non serve IPF. Il ruolo del rispondente viene assegnato in M4.

### Filtri

I filtri del segmento azzerano le celle escluse. Un intervallo di età che
taglia un gruppo quinquennale riduce la cella in proporzione alle età
singole (ad esempio `age: [18, 80]` tiene un quinto del gruppo 80-84). Un
intervallo di addetti tiene intere le classi che lo intersecano, perché
dentro la classe non c'è dettaglio.

### Quote, sovracampionamento, dimensione dei segmenti

Per ogni variabile di quota il target è la quota marginale della
popolazione filtrata, convertita in interi con il metodo dei resti maggiori.
Se una variabile è sovracampionata, le sue quote vengono dalla
configurazione; la congiunta viene riallineata con un raking a quei
marginali (popolazione di disegno) e i target delle altre variabili si
calcolano sulla popolazione di disegno, non su quella reale. Così il campione
rispecchia la popolazione di disegno in tutte le variabili e i pesi tornano
a quella reale senza marginali incompatibili.

L'avviso sulle celle piccole scatta quando una categoria ha meno di 3 casi
attesi (dimensione del segmento per quota di disegno) e propone di accorpare.
Con `allocation: proportional` le dimensioni dei segmenti seguono le
popolazioni filtrate; per segmenti di unità diverse (individui e imprese) il
risultato è legittimo ma raramente utile.

### Estrazione

Le celle vengono ordinate per le variabili di quota e campionate in modo
sistematico (passo = popolazione / n, avvio casuale), che dà già marginali
vicini ai target per effetto della stratificazione implicita. Poi un ciclo
di scambi sposta una unità alla volta dalla categoria più sovrarappresentata
a quella più sottorappresentata della stessa variabile, scegliendo le celle
in base agli scarti delle altre variabili, finché ogni categoria coincide con
il target intero. Per gli individui l'età puntuale è estratta dentro il
gruppo quinquennale in proporzione alle età singole della regione e del
sesso, entro il filtro età. Tutta la casualità passa da un generatore numpy
derivato dal seed di progetto con `SeedSequence`, uno per segmento in ordine
di configurazione: stesso seed, stesso campione.

### Pesi

I pesi di post-stratificazione nascono da un raking delle unità sui
marginali di popolazione delle variabili di quota: le distribuzioni pesate
coincidono con quelle ISTAT. `weight` somma a n, `weight_pop` alla
popolazione filtrata. Se il raking non converge (campione piccolo e
sovracampionamento forte rendono incompatibili i marginali), le variabili
non sovracampionate con il residuo peggiore vengono escluse una alla volta e
l'esclusione è dichiarata negli avvisi: la variabile sovracampionata è
sempre ricostruita. Un avviso segnala i pesi oltre cinque volte la mediana
del proprio strato di sovracampionamento e il `deff` dei pesi è riportato
nella diagnostica.

### Limiti

- L'incrocio istruzione × condizione per regione non è pubblicato: la sua
  struttura viene dal seed nazionale delle Forze di lavoro.
- Le quote nazionali per classe decennale sono conservate solo per quanto
  compatibile con i livelli censuari regionali.
- Con un segmento di 30 unità e sovracampionamento 40/35/25 su classi che in
  popolazione pesano 95/4.6/0.6, i pesi delle microimprese superano di 17
  volte quelli delle medie: è la conseguenza voluta del disegno, che va
  tenuta presente nell'analisi (deff intorno a 2.3).

## 3. Costruzione delle persone

### Fonti e provenienza

La European Social Survey, indicata nella specifica come riferimento per gli
atteggiamenti, è distribuita con licenza CC BY-NC-SA 4.0, solo per uso non
commerciale: non viene usata. Gli atteggiamenti vengono dall'indagine ISTAT
Aspetti della vita quotidiana (fiducia negli altri, soddisfazione per la
vita, uso di internet, informazione politica, pratica religiosa), il
giudizio sulle risorse economiche dall'AVQ famiglie per regione, il reddito
da EU-SILC aggregata, le caratteristiche delle imprese dal Censimento
permanente delle imprese 2022. Ogni attributo porta la propria provenienza
(`campione`, `istat`, `istat_proxy`, `ipotesi`): il codebook in
[codebook_personas.md](codebook_personas.md) elenca campo per campo valori e
fonte.

### Assegnazione

Gli attributi ISTAT sono estratti dalla distribuzione condizionata al
profilo: sesso, classe d'età e titolo di studio per l'AVQ, regione per il
giudizio economico, settore e classe di addetti per le imprese. Il reddito
combina tre distribuzioni marginali EU-SILC (quintile dato il titolo, la
condizione e la regione del principale percettore) con l'ipotesi di
indipendenza, P(q | t, c, r) ∝ P(q | t) P(q | c) P(q | r) / P(q)². Le
correlazioni fra atteggiamenti oltre la demografia non sono modellate:
fiducia e soddisfazione, ad esempio, sono indipendenti a parità di profilo.

Gli attributi senza fonte (sensibilità al prezzo, fedeltà alla marca,
propensione al rischio, apertura al nuovo, e le cinque dimensioni dello
stile di risposta) sono estratti da distribuzioni Beta con media pari a una
base più modificatori per categoria e concentrazione fissa, dichiarati nel
file `personas/priors/default.yaml`. I modificatori seguono la letteratura
sui bias di risposta: acquiescenza e "non so" crescono al diminuire del
titolo di studio e con l'età, la desiderabilità sociale con l'età e la
pratica religiosa, il tempo disponibile è maggiore per pensionati e
inattivi. Sono ipotesi, e la config può sostituire il file.

Per le imprese l'unità campionata è l'impresa: il rispondente riceve ruolo
(quote per classe di addetti, ristrette dai ruoli ammessi in config),
numero di addetti (log-uniforme nella classe), sesso ed età (quote e
intervalli per ruolo, ipotesi), titolo di studio dalla distribuzione
nazionale per sesso ed età. Relazioni con altre imprese e obiettivi
strategici vengono dal censimento; per le microimprese gli obiettivi sono
quelli delle imprese 10-49 addetti, con provenienza `istat_proxy`.

### Coerenza

Le combinazioni implausibili fra attributi assegnati in questa fase
(soddisfazione minima con risorse ottime, mai su internet con apertura al
nuovo altissima, giovane in cerca di lavoro nel quintile più alto,
responsabile acquisti in un'impresa con meno di cinque addetti) provocano
una nuova estrazione con lo stesso generatore, fino a dieci tentativi. Le
combinazioni rare ereditate dal campione (pensionato sotto i 50 anni) non
si toccano, perché le quote del campione sono vincolanti, ma vengono
contate negli avvisi.

### Narrativa

Il template Jinja2 `agents/prompts/persona_it.j2`, versionato con hash,
rende il profilo in un testo in terza persona di 100-200 parole: nome di
battesimo coerente con sesso e decennio di nascita (lista curata,
disattivabile), vita quotidiana, atteggiamenti, modo di rispondere espresso
come comportamento e mai come numero. Il testo è il system prompt
dell'agente rispondente.

### Riproducibilità

Le persone usano un ramo del seed di progetto separato da quello del
campione (`SeedSequence([seed, 4])`, un generatore per unità): cambiare i
priori non cambia il campione e viceversa. Ogni persona registra gli hash
del template, del file dei priori e delle tavole ISTAT usate.

### Limiti

- Indipendenza condizionale fra atteggiamenti, e fra reddito e
  atteggiamenti, a parità di demografia.
- Classi d'età AVQ larghe e inclusive dei minorenni nella classe più giovane.
- Sesso, età e ruolo del rispondente d'impresa sono ipotesi, non dati.
- I tratti di consumo e lo stile di risposta sono interamente ipotesi:
  servono a far emergere effetti di modalità credibili, non a misurare.

## 4. Adattamento del questionario per modalità

### Formato sorgente

Il questionario è un dato di input in YAML (schema in
`synthsurvey.questionnaire.schema`): sezioni e domande con tipo (`single`,
`multi`, `scale`, `grid`, `open`, `numeric`), opzioni, scala con etichette,
item di griglia, limiti numerici, `applies_to`, `show_if`, `dont_know`,
`randomize` con `fixed_last`, `page`. La validazione raccoglie tutti gli
errori insieme: struttura per tipo, id unici, opzioni non vuote, scale
coerenti, espressioni di routing che citano solo domande precedenti con
valori ammessi, segmenti esistenti nella configurazione.

### Routing

Le espressioni `show_if` sono valutate da un parser proprio, senza `eval`:
confronti con risposte precedenti (`q1 <= 5`, `q2 == "Prezzo"`,
`q3 in [...]`, `q4 contains "x"` per le multiple, `q5.a >= 4` per gli item
di griglia), `and`, `or`, `not`, parentesi e `answered(q)`. Una risposta
assente, "non so" o non applicabile rende falso ogni confronto: una
domanda condizionata a una risposta mancante viene saltata, come farebbe un
sistema CAWI. `next_question` restituisce la prossima domanda applicabile
al segmento e non ancora risposta; `route` ricostruisce il percorso
completo a posteriori.

### Versioni per modalità

Dal questionario sorgente si generano tre versioni con regole esplicite
(tabella in SPEC.md):

- **CAWI**: pagine (`page`, altrimenti una domanda per pagina), opzioni
  tutte visibili, "non so" come opzione in coda, griglie intere, scale con
  etichette complete.
- **CATI**: una domanda alla volta; le opzioni di singole e multiple sono
  lette in sequenza ("Le leggo le possibili risposte: ..."); le scale sono
  presentate per gli estremi ("da 1 a 10, dove 1 significa ... e 10
  significa ..."); le griglie sono spezzate in una domanda per item, con la
  scala letta al primo e una nota per ripeterla; "non so" non viene letto e
  si accetta solo se spontaneo; note all'intervistatore per domande
  sensibili e multiple.
- **CAPI**: come CATI, ma scale, griglie e liste con più di quattro opzioni
  usano il cartellino, segnalato nel testo e nella nota; le griglie restano
  intere perché il cartellino le sostiene.

Ogni domanda adattata conserva `source_id` e, per gli item spezzati,
`item_id`, così le risposte si ricompongono nel dataset lungo. L'ordine
delle opzioni per ogni intervista è deciso dal runner con `option_order`:
mescola solo se la domanda è `randomize`, la config lo consente
(`engine.randomize_option_order`) e tiene in coda le voci `fixed_last`.

### Revisione e congelamento

`synthsurvey questionnaire export` scrive YAML e Markdown per modalità, da
rivedere a mano prima del congelamento; il file sorgente e le versioni
esportate hanno un hash SHA-256 che il manifest del run registrerà in M9.

### Importazione del questionario grezzo (M6b)

`synthsurvey questionnaire import <file>` parte da un documento Word, PDF,
Excel o di testo. L'estrazione (`synthsurvey.questionnaire.extract`) è
deliberatamente semplice: paragrafi, elenchi e tabelle nell'ordine del
documento, marcatori di pagina per i PDF e di foglio per Excel, hash del
file sorgente. Non c'è OCR: un PDF senza livello di testo viene rifiutato.

L'agente importatore (prompt `agents/prompts/questionnaire_import_it.j2`)
riceve il testo e risponde con una bozza vincolata a uno schema JSON: lo
stesso contenuto del formato YAML, ma con tutti i campi espliciti e le
etichette di scala come lista di coppie, perché l'output strutturato dei
provider non ammette chiavi intere, campi facoltativi impliciti o vincoli
numerici. Il prompt descrive il formato, la sintassi di `show_if` e, punto
centrale, la traduzione delle istruzioni di salto in prosa ("se No passare
alla D5") in condizioni di visibilità sulle domande dipendenti. Oltre al
questionario il modello restituisce note di incertezza tipizzate (routing,
tipo, opzioni, testo, ipotesi, parti non trascritte) che finiscono nel
rapporto.

La bozza è convertita nel dizionario YAML e validata con il parser di M5 e
con la configurazione (segmenti citati). Gli errori tornano al modello nella
stessa conversazione per un numero limitato di giri (due di default); se
restano, lo YAML viene salvato come bozza e gli errori elencati nel rapporto.
Il rapporto Markdown riporta provenienza e hash, modello e costo, la tabella
delle domande con il riferimento nel documento, le note dell'agente e una
lista di controllo. La revisione umana resta obbligatoria: l'importazione
produce un punto di partenza verificabile, non un questionario finito.

Il caso di prova è `questionnaires/examples/mercato_v1.docx`, un Word scritto
come lo scriverebbe un istituto, con salti in prosa, griglia in tabella e
note per l'intervistatore; la prova dal vivo con il modello reale è
registrata in `docs/TODO.md` finché non è eseguita.

## 5. Livello LLM: client, cache, costi

### Interfaccia

Tutto il sistema parla con i provider attraverso `LLMClient`
(`synthsurvey.llm`): una `LLMRequest` con system prompt, messaggi, schema
JSON facoltativo per la risposta strutturata, `max_tokens`, `effort` e una
`variant`; una `LLMResponse` con testo, oggetto validato, token (ingresso,
uscita, cache letta e scritta), modello, latenza, motivo di stop, rifiuto e
id della richiesta. I provider sono `anthropic` (SDK ufficiale, client
asincrono) e `fake` (test e run a secco); `openai` è accettato dalla config
per l'ensemble di M12.

### Scelte dell'adapter Anthropic

- Risposte strutturate con `output_config.format` (JSON Schema) e
  validazione lato client; una risposta non conforme viene richiesta una
  seconda volta prima di fallire.
- Profondità di ragionamento con `output_config.effort` (`low` di default:
  rispondere a un questionario non richiede ragionamento profondo e costa
  meno). I modelli Claude attuali rifiutano `temperature`: la variabilità
  fra repliche viene dal modello stesso, e la config segnala il campo come
  ignorato.
- Prompt caching del system prompt: la narrativa della persona resta uguale
  per tutte le domande di un'intervista.
- Fallback lato server sui rifiuti di sicurezza (`fallbacks="default"`):
  una domanda sensibile rifiutata dal modello principale viene rigirata al
  modello di riserva scelto da Anthropic; il rifiuto residuo è registrato
  (`refused`) e non fa fallire l'intervista. Haiku non lo supporta.
- Retry su errori di rete, 429 e 5xx delegati all'SDK; la chiave API arriva
  solo da `ANTHROPIC_API_KEY` (file `.env` non versionato).

### Cache e riproducibilità

La cache su disco (`<output.dir>/.cache` o `engine.cache_dir`) indicizza le
risposte per hash SHA-256 della richiesta completa: provider, modello,
system prompt, messaggi, schema, `effort`, `max_tokens` e `variant`. La
variante distingue le repliche di una stessa intervista, altrimenti
identiche: senza, la cache restituirebbe la stessa risposta a tutte. Un run
ripetuto con gli stessi prompt non chiama il provider e restituisce le
stesse risposte, condizione necessaria per il congelamento di M9. I rifiuti
non vengono messi in cache.

### Concorrenza e costi

`LLMPool` applica cache, semaforo di concorrenza (`engine.concurrency`),
timeout per chiamata e contatori: richieste, hit di cache, chiamate reali,
errori, rifiuti, token e costo. I prezzi sono in `llm/prices.yaml`,
versionato con data e fonte; il costo per risposta usa le quattro categorie
di token e `engine.eur_per_usd` lo converte in euro per il confronto con
`run.budget_max_eur` in M9.

### Provider sessione (M14)

Con `provider: session` nessun modello viene chiamato: ogni richiesta
senza risposta finisce su file e il run si sospende; la sessione di Claude
Code legge le richieste (persona, regole della modalità, conversazione,
schema) e deposita risposte validate contro lo schema, poi il run riparte
dallo stesso comando grazie alla cache per impronta. È pensato per piloti
di poche decine di interviste quando manca il credito API: la qualità
dipende da chi risponde, non c'è concorrenza reale e ogni passo
sequenziale richiede un giro. I record riportano `model = session`, così
nei confronti non si mescolano con quelli dei modelli via API.

## 6. Simulazione delle modalità

### Rispondente

L'agente rispondente è un modello linguistico con un system prompt in due
parti (`agents/prompts/respondent_it.j2`): la narrativa della persona (M4)
con i tratti dello stile di risposta resi in parole, e le regole della
modalità. Il prompt chiede di interpretare la persona senza essere più
informata o più equilibrata di lei e descrive i comportamenti tipici della
modalità (nel CAWI: lettura veloce, scelta fra le prime opzioni, voti simili
nelle griglie, aperte brevi, "non so" a portata di clic, abbandono). Gli
effetti di modalità non sono imposti da regole: devono emergere dal profilo
e dal prompt, e vanno verificati nel pilota e con i dati reali (M11).

### CAWI (M7)

Ogni pagina del questionario adattato è una chiamata al modello con uno
schema JSON che elenca le domande visibili e, per ciascuna, i valori
ammessi (opzioni nell'ordine presentato, punti della scala, "non so" se
previsto). Le pagine precedenti restano nella conversazione, così il
rispondente vede le proprie risposte e resta coerente. Il routing è
valutato prima di ogni pagina; una domanda che dipende da un'altra della
stessa pagina viene mostrata in un gruppo successivo. L'ordine delle
opzioni è deciso per intervista da un generatore derivato dal seed di
progetto, dall'indice della persona, dalla modalità e dalla replica:
stessa configurazione, stesso ordine.

Le risposte vengono normalizzate e controllate oltre lo schema (limiti
numerici, numero massimo di scelte, etichette fra quelle presentate):
ciò che non è codificabile diventa non risposta. Ogni domanda e ogni item
di griglia produce un record del dataset lungo con stato (`answered`,
`dont_know`, `nonresponse`, `not_applicable`, `abandoned`), codice
rispetto all'ordine canonico, testo, ordine presentato, pagina e quota di
token della chiamata.

### CATI e CAPI (M8)

Le interviste con intervistatore procedono una domanda alla volta sulla
versione per modalità di M5 (griglie spezzate al telefono, cartellini di
persona). L'intervistatore legge la domanda con le opzioni nell'ordine
deciso dal seed; il rispondente risponde con la battuta a voce, la risposta
codificata, l'eventuale richiesta di chiarimento e il blocco dei segnali
non verbali. L'agente intervistatore (`agents/prompts/interviewer_it.j2`)
interviene solo quando serve: chiarimento chiesto, risposta non
codificabile, o un segnale osservato di intensità almeno 2 su 3. Può
accettare, chiarire o approfondire una sola volta con una domanda neutra;
dopo il suo intervento il rispondente parla di nuovo e la seconda risposta
è quella definitiva. Così la maggior parte delle domande costa una
chiamata e nessuna più di tre.

### Segnali non verbali

Vocabolario fisso: esitazione, incertezza, entusiasmo, disinteresse,
irritazione, imbarazzo, ciascuno con intensità da 0 a 3; linguaggio del
corpo in quattro campi (espressione, sguardo, postura, gesti); una nota
libera su ciò che la persona pensa davvero. Il rispondente emette tutto,
sempre: è la "verità" simulata e finisce in `nonverbal_emitted`.
L'intervistatore osserva solo ciò che la modalità permette (al telefono
niente corpo) e lo trova in `nonverbal_observed`; quando i segnali
contraddicono le parole annota `incongruence`. Con
`engine.nonverbal.enabled: false` il blocco sparisce da schema, prompt e
record, per confrontare i risultati con e senza.

Va letto come ipotesi qualitativa: non esiste una misura reale con cui
calibrarlo finché gli intervistatori umani non annotano i segnali con la
stessa griglia.

### Limiti

- La plausibilità delle risposte dipende dal modello e dal prompt: con il
  client finto i test verificano la meccanica (routing, codifica, stati,
  seed, interventi dell'intervistatore), non la qualità. I piloti con il
  modello reale sono nel TODO.
- Il CAWI non simula i tempi di compilazione né le risposte cambiate:
  i paradati disponibili sono abbandono, non risposta e token.
- Nelle interviste con intervistatore non è simulato l'abbandono a metà;
  il rifiuto del modello su una domanda produce una non risposta.
- L'effetto intervistatore è unico: non ci sono intervistatori diversi
  con stili diversi.

## 7. Disegno, repliche, ensemble, congelamento

### Piano

Il runner costruisce un piano esplicito: per ogni modello in
`engine.models`, per ogni persona, per ogni modalità assegnata, per ogni
replica. Nel disegno within-subject ogni persona risponde in tutte le
modalità abilitate; nel between-subject riceve una sola modalità, con
conteggi esatti dai resti più grandi su `modes.allocation` e una
permutazione dal ramo 9 del seed. Le repliche ripetono la stessa
intervista con una chiave di variante diversa, così la cache non le
confonde e il generatore dell'ordine delle opzioni cambia.

### Stima e budget

Prima di chiamare qualsiasi modello il runner stima token e costo a
prezzo pieno, senza cache, contando il contesto che cresce nel CAWI (le
pagine precedenti) e nel dialogo (gli ultimi otto scambi) più una quota di
interventi dell'intervistatore. La stima è volutamente prudente: se supera
`run.budget_max_eur` il run non parte. Durante il run la spesa reale dei
pool viene confrontata con il budget prima di avviare ogni intervista; se
lo supera, le interviste non iniziate vengono saltate e il manifest
registra `budget_exceeded`. Le interviste già fatte restano valide.

### Ensemble

Con più modelli in `engine.models` ogni intervista del piano viene
eseguita da ciascun modello, con pool, cache e costi separati. Il
report aggiunge una sezione che mette a confronto i modelli variabile
per variabile e ordina per divergenza (massimo meno minimo del valore
di sintesi): dove i modelli non concordano la risposta dipende dal
modello più che dal profilo, e la domanda va letta con cautela o
riformulata. L'adapter OpenAI (M12) usa risposte strutturate in
modalità `strict` con gli stessi schemi dell'adapter Anthropic, così i
due provider rispondono nello stesso formato.

### Riavvio

Ogni richiesta ha un'impronta (modello, prompt, schema, variante) e la
cache su disco conserva la risposta: un run interrotto, rilanciato con la
stessa configurazione, rifà solo le chiamate mancanti. Il secondo avvio di
un run identico costa zero chiamate.

### Manifest e congelamento

`manifest.json` contiene la configurazione completa, gli hash del file di
configurazione, del questionario, delle tavole ISTAT e dei prompt, i
modelli, il seed, il piano, la stima, le statistiche dei pool e la spesa.
`synthsurvey freeze` aggiunge l'hash di ogni file della cartella e
`frozen: true`; da quel momento il runner rifiuta di riscrivere la
cartella e `freeze --verify` segnala file modificati, mancanti o
aggiunti. Ogni correzione genera un nuovo run.

### Limiti

- La stima dei token usa costanti (caratteri per token, lunghezza delle
  risposte) tarate a mano: va confrontata con la spesa reale dei primi
  run e corretta nel codice se sbaglia di molto.
- Il controllo del budget è per intervista, non per chiamata: l'ultima
  ondata di interviste già avviate può sforare di poco.

## 8. Output, codebook e report

### Dataset

Il dataset lungo (`responses_long`) è la fonte: una riga per domanda e
item di ogni intervista, con stato, codice, testo, ordine presentato e
paradati. Il dataset largo (`responses_wide`) ne deriva: una riga per
persona × modalità × replica × modello, con gli attributi della persona e i
pesi. Le convenzioni di codifica sono nel codebook e nella SPEC; i codici
mancanti negativi distinguono "non applicabile", "non risposta", "non so"
e "abbandono", e nel file .sav sono dichiarati come valori mancanti con
etichette, così SPSS e R li trattano correttamente. Le domande aperte
restano testo, con una variabile di stato accanto.

### Codebook

`codebook.json` descrive chiavi, attributi della persona con la loro
provenienza (dato ISTAT, proxy, ipotesi), ogni variabile del largo con
etichette dei valori e mancanti, e la struttura del lungo. Il codebook è
il posto dove un analista scopre che `sensibilita_prezzo` è un'ipotesi
dichiarata e non un dato.

### Report

Il report HTML è statico, senza dipendenze esterne, con grafici SVG
generati nel codice. Ogni pagina porta l'avvertenza che i dati sono
simulati. Le sezioni: esito delle interviste per modalità (completamento,
stati, chiarimenti, approfondimenti, lunghezza delle aperte);
distribuzioni pesate per domanda; effetti di modalità rispetto al CAWI
(media o quota della risposta prevalente, differenza, mancanti) e
straightlining nelle griglie; confronto fra segmenti; stabilità fra
repliche (quota di interviste con la stessa risposta in tutte le
repliche: bassa dove il modello domina il profilo); incongruenze non
verbali per domanda e segmento; costi e chiamate.

### Limiti

- Le quote sono pesate con il peso di post-stratificazione ma senza
  intervalli di confidenza: i confronti vanno letti come descrittivi.
- La "risposta prevalente" delle singole è scelta sul totale, non per
  gruppo: nei confronti si legge la stessa opzione in tutti i gruppi.

## 9. Validazione ex post

### Dati reali

`synthsurvey validate <run> --real <csv>` accetta due formati. Il lungo ha
una riga per rispondente e domanda (`respondent_id`, `mode`, `question_id`,
`answer_code`, facoltativi `item_id`, `segment`, `weight`), con le stesse
convenzioni di codifica del simulato: indice 1..k per le singole, indici
separati da `|` per le multiple, numero per scale e numeriche, `NS` per
"non so", vuoto per non risposta; le domande assenti per un rispondente
sono non applicabili. Il largo ha una riga per rispondente e le colonne
con i nomi del dataset largo simulato. In entrambi i casi i dati vengono
portati al largo, così ogni metrica confronta colonne omonime.

### Allineamento

Si confrontano solo le modalità presenti in entrambi i dataset; quelle
presenti solo nel simulato restano etichettate come non validate. Le
variabili confrontabili sono quelle con almeno una risposta reale; i
sottogruppi sono gli attributi presenti in entrambi (segmento, classe
d'età, area, sesso, dimensione d'impresa, istruzione). I pesi reali, se
assenti, valgono 1.

### Metriche

- **Distanza per domanda**: Jensen-Shannon in base 2 (0 identiche, 1
  disgiunte) e variazione totale fra le distribuzioni pesate delle
  risposte valide, per ogni variabile codificata.
- **Valore di sintesi con intervallo**: media per scale, numeriche,
  griglie e dummy delle multiple; quota della risposta prevalente nel
  reale per le singole. L'intervallo al 95% è calcolato sul campione
  reale con l'approssimazione normale; il rapporto dice se il simulato
  cade dentro, così un valore fuori per pochi punti su 40 interviste non
  viene letto come errore del modello.
- **Correlazione**: Pearson fra i valori di sintesi simulati e reali
  sull'insieme delle variabili, quote e medie separate. Alta correlazione
  con differenze sistematiche segnala un bias di livello, non di
  ordinamento.
- **Sottogruppi**: per ogni attributo comune, differenze di media di ogni
  gruppo rispetto al primo, nel simulato e nel reale: accordo di segno e
  correlazione. Dice se le differenze fra gruppi sono riprodotte, che è
  ciò che conta per le letture per segmento.
- **Effetti di modalità**: la stessa misura con la modalità come
  variabile di gruppo, solo sulle modalità osservate anche nel reale.

### Limiti

- Gli intervalli sono normali e non tengono conto dei pesi reali né del
  disegno dell'indagine reale; con campioni piccoli vanno letti con
  prudenza.
- Nessuna correzione per confronti multipli: con molte domande qualche
  "fuori intervallo" è atteso per caso.
- Il test del criterio di M11 usa un dataset reale fittizio derivato dal
  simulato con rumore; la validazione vera richiede le interviste del
  caso di riferimento.

## 10. Anagrafiche come campione

### Dal file alle persone

Con la sorgente `lista_clienti` il campione non è estratto da una
popolazione sintetica: è l'elenco del committente. Ogni record valido
diventa un'unità con peso 1, perché l'elenco è l'universo che interessa e
non va riportato alla popolazione italiana. Il file non è mai uguale, quindi
le colonne vengono riconosciute da sinonimi (sesso, età o data di nascita,
codice fiscale, regione, provincia, codice ISTAT del comune, partita IVA,
codice ATECO, addetti, ruolo, tipologia cliente) e, dove il riconoscimento
fallisce, da una mappatura esplicita in configurazione.

Dal record si ricavano solo gli attributi utili: sesso ed età dalle colonne
o, in loro assenza, dal codice fiscale (anno, mese, giorno con l'offset di
40 per le donne); la regione dalla provincia o dalle prime tre cifre del
codice ISTAT del comune, con la tabella delle province del pacchetto; per
le imprese il settore dalla divisione ATECO e la classe dimensionale dagli
addetti. L'unità (individuo o impresa) viene dalla tipologia cliente o
dalla partita IVA; un'impresa con codice fiscale di persona è una ditta
individuale o un professionista, e il rispondente ha sesso ed età noti.
I record si deduplicano per codice cliente, codice fiscale o partita IVA:
un cliente con più forniture è una persona sola.

### ISTAT completa

Ciò che il file non dice viene estratto dalle stesse distribuzioni di M3 e
M4, condizionate a ciò che il file dice: istruzione e condizione
professionale dalla congiunta IPF per regione, sesso e gruppo d'età;
settore e classe dimensionale mancanti dalle imprese attive della regione;
reddito, atteggiamenti e stile di risposta come per le altre persone. La
provenienza `anagrafica` si aggiunge a campione, ISTAT e ipotesi e compare
nel codebook, così chi analizza sa quali tratti sono dati del cliente e
quali inferenze.

### Privacy

Nomi, cognomi, codici fiscali, indirizzi, email e telefoni non vengono
letti nel campione: il codice fiscale è usato solo per ricavare sesso ed
età e poi scartato, i nomi delle persone sintetiche vengono dalle liste del
pacchetto. L'unico legame con i record è `private/contacts_map.csv` nella
cartella del run, con un avviso a non condividerlo; il rapporto
dell'anagrafica riporta conteggi e motivi di scarto, mai valori.

### Limiti

- Un record con il solo comune e senza provincia né codice ISTAT viene
  scartato: servirebbe la tabella dei comuni, da aggiungere se capita.
- Le colonne di tipologia cliente hanno codifiche proprie di ogni azienda:
  il riconoscimento copre le più comuni (B/C, azienda/privato, business/
  consumer); negli altri casi la partita IVA decide.
- Con peso 1 i risultati descrivono l'elenco, non il mercato: il report lo
  dichiara nel codebook.
