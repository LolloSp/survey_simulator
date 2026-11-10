"""Mappature per le tavole degli atteggiamenti, del reddito e delle imprese (M4).

Fonti: Aspetti della vita quotidiana (AVQ), EU-SILC aggregata, Censimento
permanente delle imprese. Come in `codelists.py`, i codici assenti dalle
mappature vengono scartati dalla normalizzazione.
"""

# Classi d'età AVQ (variano fra quesiti: 14+ oppure 6+).
AGE_CLASS_AVQ: dict[str, str] = {
    "Y14-24": "14_24",
    "Y6-24": "6_24",
    "Y25-44": "25_44",
    "Y45-64": "45_64",
    "Y_GE65": "65_plus",
}

# Titolo di studio AVQ ed EU-SILC (CL_TITOLO_STUDIO, quattro livelli).
EDUCATION_AVQ: dict[str, str] = {
    "3": "fino_media",  # licenza elementare o nessun titolo
    "4": "fino_media",  # licenza media
    "7": "diploma",
    "11": "laurea_o_oltre",
}

# Fiducia interpersonale.
TRUST_AVQ: dict[str, str] = {"14_YESTRUST": "si_fida", "14_NOTRUST": "diffida"}

# Soddisfazione per la vita (punteggio 0-10).
LIFE_SATISFACTION_AVQ: dict[str, str] = {f"14_SAT_LIFE_{i}": str(i) for i in range(11)}

# Uso di internet negli ultimi 12 mesi, per frequenza.
INTERNET_AVQ: dict[str, str] = {
    "6_INTTUTTI": "quotidiano",
    "6_INT_1P_SETT": "occasionale",
    "6_INT_QV_MESE": "occasionale",
    "6_INT_QV_ANNO": "occasionale",
    "6_INTNO": "mai",
}

# Frequenza con cui ci si informa di politica.
POLITICAL_INFO_AVQ: dict[str, str] = {
    "14_INF_POL_EVERY": "quotidiana",
    "14_INF_POL_SW": "settimanale",
    "14_INF_POL_1W": "settimanale",
    "14_INF_POL_SM": "saltuaria",
    "14_INF_POL_SY": "saltuaria",
    "14_INF_POL_NEV": "mai",
}

# Frequenza di un luogo di culto; "saltuaria" è il residuo rispetto al totale 6+.
RELIGION_AVQ: dict[str, str] = {"6_WEEK_RELIG": "settimanale", "6_NEVER_RELIG": "mai"}
RELIGION_RESIDUAL = "saltuaria"

# Giudizio delle famiglie sulle risorse economiche negli ultimi 12 mesi (per regione).
ECONOMIC_JUDGEMENT_AVQ: dict[str, str] = {
    "HOUS_EC_RESVG": "ottime",
    "HOUS_EC_RESAD": "adeguate",
    "HOUS_EC_RESSC": "scarse",
    "HOUS_EC_RESAS": "insufficienti",
}

# Quintili di reddito equivalente (EU-SILC): dimensioni del principale percettore.
INCOME_EDUCATION_CODES: tuple[str, ...] = ("3", "4", "7", "11")
INCOME_STATUS_CODES: dict[str, str] = {
    "1A": "indipendente",
    "1B": "dipendente",
    "2A": "pensionato",
    "2B": "in_cerca",
    "2C": "altro_inattivo",
}
INCOME_QUINTILES: tuple[str, ...] = ("1", "2", "3", "4", "5")

# Censimento permanente delle imprese: sezioni ATECO -> settori, classi di addetti.
SECTOR_BY_SECTION: dict[str, str] = {
    "B": "industria",
    "C": "industria",
    "D": "industria",
    "E": "industria",
    "F": "costruzioni",
    "G": "commercio",
    "H": "trasporti_turismo",
    "I": "trasporti_turismo",
    "J": "servizi_imprese",
    "K": "servizi_imprese",
    "L": "servizi_imprese",
    "M": "servizi_imprese",
    "N": "servizi_imprese",
    "P": "altri_servizi",
    "Q": "altri_servizi",
    "R": "altri_servizi",
    "S": "altri_servizi",
}
SIZE_CLASS_CENSUS: dict[str, str] = {
    "W3_9": "micro",
    "W10_19": "piccola",
    "W20_49": "piccola",
    "W50_99": "media",
    "W100_249": "media",
}
FIRM_OBJECTIVES: dict[str, str] = {
    "INCRINVNEWTEC": "nuove_tecnologie",
    "ACCESMARKSEG": "nuovi_mercati",
    "RANGEGOODSERV": "ampliare_gamma",
    "INCRACTABR": "estero",
    "ACTSOCENV": "responsabilita_sociale",
    "DEFCOMPPOS": "difendere_posizione",
}
