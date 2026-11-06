"""Narrativa in italiano della persona: dal profilo strutturato al testo del template."""

import hashlib
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from synthsurvey.personas.schema import Persona, level3

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "agents" / "prompts"
TEMPLATE_NAME = "persona_it.j2"

REGION_NAMES: dict[str, str] = {
    "piemonte": "Piemonte",
    "valle_daosta": "Valle d'Aosta",
    "lombardia": "Lombardia",
    "liguria": "Liguria",
    "trentino_alto_adige": "Trentino-Alto Adige",
    "veneto": "Veneto",
    "friuli_venezia_giulia": "Friuli-Venezia Giulia",
    "emilia_romagna": "Emilia-Romagna",
    "toscana": "Toscana",
    "umbria": "Umbria",
    "marche": "Marche",
    "lazio": "Lazio",
    "abruzzo": "Abruzzo",
    "molise": "Molise",
    "campania": "Campania",
    "puglia": "Puglia",
    "basilicata": "Basilicata",
    "calabria": "Calabria",
    "sicilia": "Sicilia",
    "sardegna": "Sardegna",
}

SECTOR_NAMES: dict[str, str] = {
    "industria": "un'impresa industriale",
    "costruzioni": "un'impresa di costruzioni",
    "commercio": "un'impresa commerciale",
    "trasporti_turismo": "un'impresa di trasporti o turismo",
    "servizi_imprese": "un'impresa di servizi alle imprese",
    "altri_servizi": "un'impresa di servizi alla persona",
}

OBJECTIVE_NAMES: dict[str, str] = {
    "nuove_tecnologie": "investire in nuove tecnologie",
    "nuovi_mercati": "entrare in nuovi segmenti di mercato",
    "ampliare_gamma": "ampliare la gamma di prodotti o servizi",
    "estero": "crescere all'estero",
    "responsabilita_sociale": "rafforzare la responsabilità sociale e ambientale",
    "difendere_posizione": "difendere la posizione competitiva",
}


def _g(sex: str, m: str, f: str) -> str:
    return f if sex == "f" else m


def template_hash() -> str:
    return hashlib.sha256((TEMPLATE_DIR / TEMPLATE_NAME).read_bytes()).hexdigest()


def narrative_context(p: Persona) -> dict[str, Any]:
    s = p.sex
    ctx: dict[str, Any] = {
        "nome": p.name or _g(s, "Un uomo", "Una donna"),
        "eta": p.age,
        "sesso": s,
        "regione": REGION_NAMES.get(p.region, p.region),
        "firm": p.firm is not None,
    }
    edu = {
        "fino_media": _g(s, "ha finito la scuola dell'obbligo", "ha finito la scuola dell'obbligo"),
        "diploma": _g(s, "è diplomato", "è diplomata"),
        "laurea_o_oltre": _g(s, "è laureato", "è laureata"),
    }
    ctx["istruzione_frase"] = edu[p.education or "diploma"]
    lavoro = {
        "occupato": "lavora",
        "in_cerca": "al momento cerca lavoro",
        "pensionato": _g(s, "è in pensione", "è in pensione"),
        "altro_inattivo": "non lavora",
    }
    ctx["lavoro_frase"] = lavoro[p.employment or "occupato"]
    reddito = {
        1: "la famiglia ha un reddito tra i più bassi",
        2: "la famiglia ha un reddito modesto",
        3: "la famiglia ha un reddito nella media",
        4: "la famiglia ha un reddito sopra la media",
        5: "la famiglia ha un reddito tra i più alti",
    }
    ctx["reddito_frase"] = reddito[p.income_quintile]
    giudizio = {
        "ottime": "le risorse economiche sono giudicate ottime",
        "adeguate": "le risorse economiche sono giudicate adeguate",
        "scarse": "le risorse economiche sono giudicate scarse",
        "insufficienti": "le risorse economiche sono giudicate del tutto insufficienti",
    }
    ctx["giudizio_frase"] = giudizio[p.economic_judgement]
    if p.firm is not None:
        f = p.firm
        ruolo = {
            "titolare": _g(s, "è il titolare", "è la titolare"),
            "amministratore": _g(s, "è l'amministratore", "è l'amministratrice"),
            "responsabile_acquisti": _g(
                s, "è il responsabile acquisti", "è la responsabile acquisti"
            ),
            "altro": "lavora con un ruolo di responsabilità in",
        }
        ctx["ruolo_frase"] = ruolo[f.respondent_role]
        taglia = {"micro": "piccolissima", "piccola": "piccola", "media": "media"}[f.size_class]
        ctx["impresa_frase"] = f"{SECTOR_NAMES[f.sector]} {taglia} con {f.employees} addetti"
        dettagli = []
        if f.with_relations:
            dettagli.append("L'impresa lavora stabilmente con altre imprese")
        else:
            dettagli.append("L'impresa lavora per lo più da sola")
        if f.objectives:
            obiettivi = ", ".join(OBJECTIVE_NAMES[o] for o in f.objectives[:3])
            dettagli.append(f"negli ultimi anni ha puntato a {obiettivi}")
        else:
            dettagli.append("negli ultimi anni non ha cambiato strategia")
        ctx["impresa_dettagli"] = "; ".join(dettagli) + "."
    a = p.attitudes
    ctx["fiducia_frase"] = (
        "pensa che di gran parte della gente ci si possa fidare"
        if a.trust == "si_fida"
        else "pensa che con la gente bisogna stare molto attenti"
    )
    ctx["internet_frase"] = {
        "quotidiano": "usa internet ogni giorno",
        "occasionale": "usa internet ogni tanto",
        "mai": "non usa internet",
    }[a.internet]
    ctx["politica_frase"] = {
        "quotidiana": "segue la politica tutti i giorni",
        "settimanale": "segue la politica qualche volta a settimana",
        "saltuaria": "segue la politica di rado",
        "mai": "non segue la politica",
    }[a.political_info]
    ctx["religione_frase"] = {
        "settimanale": "frequenta un luogo di culto ogni settimana",
        "saltuaria": "frequenta un luogo di culto solo in qualche occasione",
        "mai": "non frequenta luoghi di culto",
    }[a.religion]
    if a.life_satisfaction >= 8:
        ctx["soddisfazione_frase"] = (
            "si dice molto soddisfatt" + _g(s, "o", "a") + " della propria vita"
        )
    elif a.life_satisfaction >= 6:
        ctx["soddisfazione_frase"] = (
            "si dice abbastanza soddisfatt" + _g(s, "o", "a") + " della propria vita"
        )
    elif a.life_satisfaction >= 4:
        ctx["soddisfazione_frase"] = "ha sentimenti contrastanti sulla propria vita"
    else:
        ctx["soddisfazione_frase"] = "è poco soddisfatt" + _g(s, "o", "a") + " della propria vita"
    prezzo = {
        "basso": "guarda poco al prezzo",
        "medio": "confronta i prezzi senza farne un'ossessione",
        "alto": "guarda prima di tutto al prezzo",
    }
    ctx["prezzo_frase"] = prezzo[level3(a.sensibilita_prezzo)]
    fedelta = {
        "basso": "cambia marca o fornitore senza problemi",
        "medio": "tende a restare con chi conosce ma può cambiare",
        "alto": "resta fedele alle marche e ai fornitori di sempre",
    }
    ctx["fedelta_frase"] = fedelta[level3(a.fedelta_marca)]
    rischio = {
        "basso": "evita le scelte incerte",
        "medio": "accetta qualche rischio se ne vale la pena",
        "alto": "non ha paura di rischiare",
    }
    ctx["rischio_frase"] = rischio[level3(a.propensione_rischio)]
    novita = {
        "basso": "diffida delle novità",
        "medio": "prova le novità quando gliene parlano bene",
        "alto": "è tra i primi a provare le novità",
    }
    ctx["novita_frase"] = novita[level3(a.apertura_novita)]
    r = p.response_style
    lab = r.labels()
    ctx["acquiescenza_frase"] = {
        "basso": "non esita a dissentire dalle affermazioni che le vengono proposte"
        if s == "f"
        else "non esita a dissentire dalle affermazioni che gli vengono proposte",
        "medio": "valuta ogni affermazione prima di dirsi d'accordo",
        "alto": "tende a dirsi d'accordo con quasi tutto ciò che le viene proposto"
        if s == "f"
        else "tende a dirsi d'accordo con quasi tutto ciò che gli viene proposto",
    }[lab["acquiescenza"]]
    ctx["desiderabilita_frase"] = {
        "basso": "dice quello che pensa anche se fa brutta figura",
        "medio": "qualche volta addolcisce le risposte per fare buona impressione",
        "alto": "tiene molto a fare buona impressione e lo si sente nelle risposte",
    }[lab["desiderabilita_sociale"]]
    ctx["nonso_frase"] = {
        "basso": "ha quasi sempre un'opinione e la esprime",
        "medio": "su qualche argomento preferisce non sbilanciarsi",
        "alto": "spesso risponde che non sa o preferisce non rispondere",
    }[lab["non_so"]]
    ctx["tempo_frase"] = {
        "basso": "ha poco tempo e vuole finire in fretta",
        "medio": "concede un tempo ragionevole all'intervista",
        "alto": "ha tutto il tempo che serve e non ha fretta",
    }[lab["tempo_disponibile"]]
    ctx["loquacita_frase"] = {
        "basso": "risponde con poche parole",
        "medio": "risponde in modo misurato",
        "alto": "si dilunga volentieri nelle risposte aperte",
    }[lab["loquacita"]]
    return ctx


_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
    autoescape=False,
)


def eufonia(testo: str) -> str:
    """Congiunzioni eufoniche: "e è" -> "ed è", "a ampliare" -> "ad ampliare"."""
    testo = re.sub(r"(?<![\w'])e (?=[eèEÈ])", "ed ", testo)
    return re.sub(r"(?<![\w'])a (?=[aàAÀ])", "ad ", testo)


def render_narrative(p: Persona) -> str:
    template = _env.get_template(TEMPLATE_NAME)
    testo = template.render(**narrative_context(p))
    return eufonia(" ".join(line.strip() for line in testo.splitlines() if line.strip()))
