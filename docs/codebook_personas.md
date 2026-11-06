# Codebook delle persone

Ogni persona porta, per ciascun attributo, una **provenienza**:

| Provenienza | Significato |
| --- | --- |
| `campione` | dal campione di M3: distribuzione congiunta ISTAT (IPF) ed estrazione per quote |
| `istat` | estratto dalla distribuzione ISTAT condizionata al profilo (sesso, classe d'età, titolo; regione; settore e classe) |
| `istat_proxy` | distribuzione ISTAT di un gruppo vicino: per le microimprese gli obiettivi strategici sono quelli delle imprese 10-49 addetti |
| `ipotesi` | priori dichiarati in `personas/priors/default.yaml`, nessuna fonte statistica |

Nel report e nelle analisi gli attributi `ipotesi` vanno trattati come
assunzioni da verificare, mai come misure.

## Identificativi

| Campo | Tipo | Note |
| --- | --- | --- |
| `persona_id` | `p_00001`… | progressivo nell'ordine del campione |
| `unit_id` | stringa | unità del campione di M3 |
| `segment`, `source` | stringa | dalla configurazione |
| `weight`, `weight_pop` | float | pesi del campione (somma a n e alla popolazione filtrata) |

## Demografia

| Campo | Valori | Provenienza |
| --- | --- | --- |
| `region`, `macro_area` | 20 regioni, 5 macro-aree | campione (per le imprese: sede) |
| `sex` | m, f | campione; imprese: ipotesi (quota di donne per ruolo) |
| `age`, `age_band` | 18-100; 18_24 … 65_plus | campione; imprese: ipotesi (intervallo per ruolo) |
| `education` | fino_media, diploma, laurea_o_oltre | campione; imprese: istat (Forze di lavoro per sesso ed età) |
| `employment` | occupato, in_cerca, pensionato, altro_inattivo | campione; imprese: sempre occupato |
| `income_quintile` | 1-5 | istat: EU-SILC, combinazione di titolo, condizione e regione del principale percettore (ipotesi di indipendenza) |
| `economic_judgement` | ottime, adeguate, scarse, insufficienti | istat: AVQ famiglie per regione |

## Impresa (solo segmenti con sorgente `istat_imprese`)

| Campo | Valori | Provenienza |
| --- | --- | --- |
| `firm.sector` | 6 settori ATECO accorpati | campione |
| `firm.size_class` | micro, piccola, media | campione |
| `firm.employees` | intero nei limiti della classe | ipotesi (log-uniforme) |
| `firm.respondent_role` | titolare, amministratore, responsabile_acquisti, altro | ipotesi (quote per classe), ristretto dalla config |
| `firm.with_relations` | bool | istat: Censimento imprese 2022 per settore e classe |
| `firm.objectives` | lista fra nuove_tecnologie, nuovi_mercati, ampliare_gamma, estero, responsabilita_sociale, difendere_posizione | istat (10+ addetti), istat_proxy per le micro |

## Atteggiamenti

| Campo | Valori | Provenienza |
| --- | --- | --- |
| `attitudes.trust` | si_fida, diffida | istat: AVQ per sesso, classe d'età, titolo |
| `attitudes.life_satisfaction` | 0-10 | istat: AVQ |
| `attitudes.internet` | quotidiano, occasionale, mai | istat: AVQ |
| `attitudes.political_info` | quotidiana, settimanale, saltuaria, mai | istat: AVQ |
| `attitudes.religion` | settimanale, saltuaria, mai | istat: AVQ (saltuaria come residuo) |
| `attitudes.sensibilita_prezzo` | 0-1 | ipotesi: Beta, modificata da quintile di reddito e giudizio economico |
| `attitudes.fedelta_marca` | 0-1 | ipotesi: Beta, modificata da età e uso di internet |
| `attitudes.propensione_rischio` | 0-1 | ipotesi: Beta, modificata da età, sesso, reddito |
| `attitudes.apertura_novita` | 0-1 | ipotesi: Beta, modificata da età, titolo, internet |

Le classi d'età AVQ (14-24 o 6-24, 25-44, 45-64, 65+) sono più larghe
delle fasce delle persone; la classe più giovane include minorenni e viene
usata per i 18-24enni come approssimazione.

## Stile di risposta (tutti `ipotesi`)

| Campo | Significato | Modificatori |
| --- | --- | --- |
| `response_style.acquiescenza` | tendenza a concordare con le affermazioni | titolo (−), età (+) |
| `response_style.desiderabilita_sociale` | risposte socialmente apprezzate | età (+), pratica religiosa (+), titolo (−); imprese: ruolo |
| `response_style.non_so` | propensione al "non so" | titolo (−), età (+), informazione politica (−) |
| `response_style.tempo_disponibile` | tempo e pazienza per l'intervista | condizione, età; imprese: ruolo e classe |
| `response_style.loquacita` | lunghezza delle risposte aperte | titolo (+), sesso, informazione politica (+) |

I valori in [0, 1] vengono resi in narrativa con tre livelli (basso sotto
0,35, medio, alto da 0,65) e mai come numeri.

## Narrativa

`narrative`: testo in italiano di 100-200 parole prodotto dal template
`agents/prompts/persona_it.j2`, usato come system prompt dell'agente
rispondente. Contiene nome (se abilitato), età, regione, istruzione,
lavoro, reddito e giudizio economico, impresa e ruolo, atteggiamenti,
tratti e stile di risposta espressi come comportamenti.

`source_versions`: hash SHA-256 del template, del file dei priori e di ogni
tavola ISTAT nel manifest al momento della generazione.
