"""Mappature dai codici ISTAT alle categorie canoniche del progetto.

Ogni dizionario mappa un codice sorgente a una categoria di
`survey_simulator.population.categories`. I codici non presenti vengono scartati
dalla normalizzazione (totali, aggregati intermedi, categorie fuori ambito).
"""

from survey_simulator.population import categories as cat

# Regioni (codelist CL_ITTER107, codici NUTS2) -> (slug, macro_area)
REGIONS: dict[str, tuple[str, str]] = {
    "ITC1": ("piemonte", "nord_ovest"),
    "ITC2": ("valle_daosta", "nord_ovest"),
    "ITC4": ("lombardia", "nord_ovest"),
    "ITC3": ("liguria", "nord_ovest"),
    "ITDA": ("trentino_alto_adige", "nord_est"),
    "ITD3": ("veneto", "nord_est"),
    "ITD4": ("friuli_venezia_giulia", "nord_est"),
    "ITD5": ("emilia_romagna", "nord_est"),
    "ITE1": ("toscana", "centro"),
    "ITE2": ("umbria", "centro"),
    "ITE3": ("marche", "centro"),
    "ITE4": ("lazio", "centro"),
    "ITF1": ("abruzzo", "sud"),
    "ITF2": ("molise", "sud"),
    "ITF3": ("campania", "sud"),
    "ITF4": ("puglia", "sud"),
    "ITF5": ("basilicata", "sud"),
    "ITF6": ("calabria", "sud"),
    "ITG1": ("sicilia", "isole"),
    "ITG2": ("sardegna", "isole"),
}
REGION_CODES: tuple[str, ...] = tuple(REGIONS)

# Sesso: popolazione residente usa 1/2, censimento usa M/F.
SEX_NUMERIC: dict[str, str] = {"1": "m", "2": "f"}
SEX_LETTER: dict[str, str] = {"M": "m", "F": "f"}

# Titolo di studio del Censimento permanente (CL_TITOLO_STUDIO).
EDUCATION_CENSUS: dict[str, str] = {
    "NED": "fino_media",  # nessun titolo (analfabeti e alfabeti senza titolo)
    "PSE": "fino_media",  # licenza elementare
    "LSE": "fino_media",  # licenza media o avviamento professionale
    "USE_IF": "diploma",  # diploma di istruzione secondaria di II grado o qualifica
    "BL": "laurea_o_oltre",  # ITS o terziario di primo livello
    "ML_RDD": "laurea_o_oltre",  # terziario di secondo livello e dottorato
}
EDUCATION_CENSUS_TOTAL = "ALL"

# Titolo di studio delle Forze di lavoro (stessa codelist, codici aggregati).
EDUCATION_LFS: dict[str, str] = {
    "13": "fino_media",  # nessun titolo, elementare, media
    "7": "diploma",
    "11": "laurea_o_oltre",  # laurea e post-laurea
}
EDUCATION_LFS_TOTAL = "99"

# Condizione professionale del Censimento permanente (CL_FORZE_LAV).
EMPLOYMENT_CENSUS: dict[str, str] = {
    "1": "occupato",
    "12": "in_cerca",
    "24": "pensionato",  # percettore di pensione da lavoro
    "5": "altro_inattivo",  # studente
    "4": "altro_inattivo",  # casalinga/o
    "7": "altro_inattivo",  # in altra condizione
}
EMPLOYMENT_CENSUS_TOTAL = "99"

# Classi d'età del censimento (CL_ETA1) -> etichette delle tavole normalizzate.
AGE_CLASS_CENSUS_EDU: dict[str, str] = {
    "Y9-24": "9_24",
    "Y25-49": "25_49",
    "Y50-64": "50_64",
    "Y_GE65": "65_plus",
}
AGE_CLASS_CENSUS_EMP: dict[str, str] = {
    "Y15-24": "15_24",
    "Y25-49": "25_49",
    "Y50-64": "50_64",
    "Y_GE65": "65_plus",
}
AGE_CLASS_LFS: dict[str, str] = {
    "Y15-24": "15_24",
    "Y25-34": "25_34",
    "Y35-44": "35_44",
    "Y45-54": "45_54",
    "Y55-64": "55_64",
    "Y65-89": "65_89",
}

# Classi di addetti ASIA (CL_CLLVT).
SIZE_CLASS_ASIA: dict[str, str] = {
    "W0_9": "micro",
    "W10_49": "piccola",
    "W50_249": "media",
    "W_GE250": cat.SIZE_CLASS_LARGE,
}

# Divisioni ATECO 2007 (2 cifre) -> settori del progetto. Esclusi: A (01-03),
# O (84), T (97-98), U (99), coerentemente con il registro ASIA.
_SECTOR_RANGES: tuple[tuple[int, int, str], ...] = (
    (5, 39, "industria"),  # B, C, D, E
    (41, 43, "costruzioni"),  # F
    (45, 47, "commercio"),  # G
    (49, 56, "trasporti_turismo"),  # H, I
    (58, 82, "servizi_imprese"),  # J, K, L, M, N
    (85, 96, "altri_servizi"),  # P, Q, R, S
)


def sector_for_division(code: str) -> str | None:
    """Settore del progetto per una divisione ATECO a due cifre, None se esclusa."""
    if not (len(code) == 2 and code.isdigit()):
        return None
    n = int(code)
    for lo, hi, sector in _SECTOR_RANGES:
        if lo <= n <= hi:
            return sector
    return None


SECTOR_BY_DIVISION: dict[str, str] = {
    f"{n:02d}": s for n in range(1, 100) if (s := sector_for_division(f"{n:02d}")) is not None
}


def age_from_code(code: str) -> int | None:
    """Età in anni da un codice CL_ETA1 a età singola; 100 per "Y_GE100"; None altrimenti."""
    if code == "Y_GE100":
        return 100
    if code.startswith("Y") and code[1:].isdigit():
        return int(code[1:])
    return None


def age_band(age: int) -> str:
    """Fascia d'età del progetto per un'età in anni (>= 18)."""
    if age < 18:
        raise ValueError(f"età {age} fuori dal campo di osservazione (>= 18)")
    for band in cat.AGE_BANDS:
        if band.endswith("_plus"):
            return band
        lo, hi = (int(x) for x in band.split("_"))
        if lo <= age <= hi:
            return band
    raise AssertionError("fasce d'età non contigue")
