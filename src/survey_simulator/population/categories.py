"""Categorie canoniche delle variabili di quota e dei filtri.

Sono l'unico punto in cui le categorie vengono definite: il registro delle
sorgenti (config) e la normalizzazione dei dati ISTAT (population.istat) le
importano da qui, così config e dati non possono divergere.
"""

SEX: tuple[str, ...] = ("m", "f")

# Fasce d'età delle persone (dal campione in poi).
AGE_BANDS: tuple[str, ...] = ("18_24", "25_34", "35_44", "45_54", "55_64", "65_plus")

MACRO_AREAS: tuple[str, ...] = ("nord_ovest", "nord_est", "centro", "sud", "isole")

REGIONS: tuple[str, ...] = (
    "piemonte",
    "valle_daosta",
    "lombardia",
    "liguria",
    "trentino_alto_adige",
    "veneto",
    "friuli_venezia_giulia",
    "emilia_romagna",
    "toscana",
    "umbria",
    "marche",
    "lazio",
    "abruzzo",
    "molise",
    "campania",
    "puglia",
    "basilicata",
    "calabria",
    "sicilia",
    "sardegna",
)

EDUCATION: tuple[str, ...] = ("fino_media", "diploma", "laurea_o_oltre")

EMPLOYMENT: tuple[str, ...] = ("occupato", "in_cerca", "pensionato", "altro_inattivo")

SECTORS: tuple[str, ...] = (
    "industria",
    "costruzioni",
    "commercio",
    "trasporti_turismo",
    "servizi_imprese",
    "altri_servizi",
)

# Classi dimensionali ISTAT (addetti). "grande" esiste nei dati ma non è
# una PMI: resta disponibile per una futura sorgente "grandi imprese".
SIZE_CLASS_BOUNDS: dict[str, tuple[int, int]] = {
    "micro": (1, 9),
    "piccola": (10, 49),
    "media": (50, 249),
}
SIZE_CLASSES_PMI: tuple[str, ...] = tuple(SIZE_CLASS_BOUNDS)
SIZE_CLASS_LARGE = "grande"

RESPONDENT_ROLES: tuple[str, ...] = ("titolare", "responsabile_acquisti", "amministratore", "altro")
