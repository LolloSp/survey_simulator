# Metodologia

Documento in costruzione: ogni sezione viene scritta nella milestone che la
implementa (vedi Roadmap in [SPEC.md](SPEC.md)).

1. Fonti ISTAT e versionamento delle tabelle (M2): sotto
2. Generazione della popolazione: IPF/raking, quote, pesi (M3)
3. Costruzione delle persone: atteggiamenti, stile di risposta, narrativa (M4)
4. Adattamento del questionario per modalità (M5)
5. Simulazione delle modalità ed effetti attesi dalla letteratura (M7, M8)
6. Segnali non verbali: vocabolario e limiti interpretativi (M8)
7. Disegno, repliche, ensemble, congelamento (M9)
8. Metriche di validazione ex post (M11)

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
