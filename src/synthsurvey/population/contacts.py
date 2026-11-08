"""Anagrafiche del committente come campione (sorgente `lista_clienti`, M13).

Il file (CSV o Excel) non è mai uguale: le colonne vengono riconosciute da
sinonimi, con una mappatura esplicita in configurazione quando serve. Da
ogni riga si ricavano solo gli attributi che servono alla persona sintetica
(sesso, età, territorio, settore, dimensione, ruolo): nomi, codici fiscali,
indirizzi e contatti non entrano mai nel risultato. Il codice fiscale è
usato solo per ricavare sesso ed età, poi scartato.
"""

import csv
import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl
import yaml

from synthsurvey.population import categories as cat
from synthsurvey.population.istat import codelists as cl

PROVINCE_FILE = Path(__file__).parent / "province_it.yaml"

CANONICAL: tuple[str, ...] = (
    "record_id",
    "client_type",
    "sex",
    "age",
    "birth_date",
    "fiscal_code",
    "region",
    "province",
    "comune_code",
    "cap",
    "vat",
    "ateco",
    "employees",
    "role",
)

# Sinonimi normalizzati (minuscolo, solo lettere e cifre). Il primo che compare
# nell'intestazione vince; la mappatura esplicita ha la precedenza.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "record_id": ("codicecliente", "idcliente", "clienteid", "codcliente", "customerid", "id"),
    "client_type": (
        "idtipologiacliente",
        "tipologiacliente",
        "tipocliente",
        "tipologia",
        "segmento",
        "categoriacliente",
        "clienttype",
    ),
    "sex": ("sesso", "genere", "sex", "gender"),
    "age": ("eta", "anni", "age"),
    "birth_date": ("datanascita", "datadinascita", "nascita", "birthdate", "dob", "natoil"),
    "fiscal_code": ("codicefiscale", "codfiscale", "codfisc", "cf", "fiscalcode", "taxcode"),
    "region": ("regione", "region", "regionecliente"),
    "province": (
        "siglaprovincia",
        "provincia",
        "provinciacliente",
        "prov",
        "province",
        "siglaprov",
        "provinciaresidenza",
    ),
    "comune_code": ("istatcomune", "codiceistat", "codiceistatcomune", "codicecomune", "istat"),
    "cap": ("cap", "capcliente", "codicepostale", "postalcode", "zip"),
    "vat": ("partitaiva", "piva", "pi", "vat", "vatnumber"),
    "ateco": ("codiceateco", "ateco", "codateco", "nace", "settoreateco"),
    "employees": ("addetti", "numeroaddetti", "dipendenti", "numerodipendenti", "employees"),
    "role": ("ruolo", "qualifica", "ruolorispondente", "role", "posizione"),
}

# Colonne che non vengono mai lette (dati personali o inutili): servono solo a
# non confonderle con i sinonimi.
NEVER_READ_HINTS = ("nome", "cognome", "email", "mail", "telefono", "cellulare", "pec", "iban")

INDIVIDUAL_TYPES = {
    "c",
    "d",
    "consumer",
    "privato",
    "privati",
    "persona",
    "personafisica",
    "residenziale",
    "domestico",
    "famiglia",
    "household",
}
FIRM_TYPES = {
    "b",
    "business",
    "azienda",
    "aziende",
    "impresa",
    "imprese",
    "societa",
    "pmi",
    "company",
    "ditta",
    "partitaiva",
    "pa",
    "ente",
}
MESI_CF = "ABCDEHLMPRST"
CF_RE = re.compile(r"^[A-Z]{6}(\d{2})([A-Z])(\d{2})[A-Z]\d{3}[A-Z]$")
AGE_MIN, AGE_MAX = 18, 100


class ContactsError(Exception):
    """File di anagrafiche assente, illeggibile o senza colonne utilizzabili."""


def normalize_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _ascii(str(h)).lower())


def _ascii(text: str) -> str:
    """Senza accenti e segni diacritici (Forlì -> Forli)."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _norm_value(v: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _ascii(str(v)).lower()) if v is not None else ""


def parse_int(v: Any) -> int | None:
    """Intero non negativo da numero o testo; None se non interpretabile."""
    if v is None or v == "":
        return None
    try:
        n = int(float(str(v).replace(",", ".")))
    except ValueError:
        return None
    return n if n >= 0 else None


# --------------------------------------------------------------------------- #
# Province e regioni
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ProvinceTable:
    by_sigla: dict[str, tuple[str, str]]  # sigla -> (nome, regione)
    by_name: dict[str, str]  # nome normalizzato -> sigla
    by_code: dict[str, str]  # codice ISTAT provincia -> sigla
    aliases: dict[str, str]

    def sigla(self, text: str) -> str | None:
        t = _ascii(str(text)).strip().upper()
        if t in self.by_sigla:
            return t
        if t in self.aliases:
            return self.aliases[t]
        n = _norm_value(t)
        return self.by_name.get(n) or self.aliases.get(n.upper())

    def region_of_sigla(self, sigla: str) -> str | None:
        voce = self.by_sigla.get(sigla.upper())
        return voce[1] if voce else None

    def region_of_comune_code(self, code: str) -> tuple[str, str] | None:
        """(regione, sigla) dalle prime tre cifre del codice ISTAT del comune."""
        digits = re.sub(r"\D", "", str(code))
        if len(digits) < 6:
            digits = digits.zfill(6)
        prov = digits[:3]
        sigla = self.by_code.get(prov)
        if sigla is None:
            return None
        return self.by_sigla[sigla][1], sigla


_PROVINCES: ProvinceTable | None = None


def load_provinces(path: Path = PROVINCE_FILE) -> ProvinceTable:
    global _PROVINCES
    if _PROVINCES is not None and path == PROVINCE_FILE:
        return _PROVINCES
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    by_sigla: dict[str, tuple[str, str]] = {}
    by_name: dict[str, str] = {}
    by_code: dict[str, str] = {}
    for chiave, voce in raw["provinces"].items():
        sigla = "NO" if chiave is False else str(chiave)  # YAML 1.1 legge NO come falso
        if voce["region"] not in cat.REGIONS:
            raise ContactsError(f"provincia {sigla}: regione sconosciuta {voce['region']}")
        by_sigla[sigla] = (voce["name"], voce["region"])
        by_name[_norm_value(voce["name"])] = sigla
        by_code[str(voce["code"])] = sigla
    for code, sigla in (raw.get("legacy_codes") or {}).items():
        by_code[str(code)] = sigla
    aliases = {_ascii(str(k)).upper(): str(v) for k, v in (raw.get("aliases") or {}).items()}
    table = ProvinceTable(by_sigla, by_name, by_code, aliases)
    if path == PROVINCE_FILE:
        _PROVINCES = table
    return table


REGION_CODE_BY_SLUG: dict[str, str] = {slug: code for code, (slug, _m) in cl.REGIONS.items()}
MACRO_BY_SLUG: dict[str, str] = {slug: macro for _c, (slug, macro) in cl.REGIONS.items()}


def region_slug(text: str) -> str | None:
    n = _norm_value(text)
    for slug in cat.REGIONS:
        if n == _norm_value(slug) or n == _norm_value(slug.replace("_", " ")):
            return slug
    alias = {
        "trentino": "trentino_alto_adige",
        "trentinoaltoadigesudtirol": "trentino_alto_adige",
        "altoadige": "trentino_alto_adige",
        "friuli": "friuli_venezia_giulia",
        "emilia": "emilia_romagna",
        "valledaosta": "valle_daosta",
        "valleedaoste": "valle_daosta",
        "aosta": "valle_daosta",
    }
    return alias.get(n)


# --------------------------------------------------------------------------- #
# Derivazioni dai singoli campi
# --------------------------------------------------------------------------- #


def parse_sex(v: Any) -> str | None:
    n = _norm_value(v)
    if n in ("m", "maschio", "male", "uomo", "1"):
        return "m"
    if n in ("f", "femmina", "female", "donna", "2"):
        return "f"
    return None


def parse_age(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        n = int(float(str(v).replace(",", ".")))
    except ValueError:
        return None
    return n if 0 < n < 130 else None


def parse_birth_date(v: Any, reference: date) -> int | None:
    d: date | None = None
    if isinstance(v, datetime):
        d = v.date()
    elif isinstance(v, date):
        d = v
    elif isinstance(v, str) and v.strip():
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
            try:
                d = datetime.strptime(v.strip()[:10], fmt).date()
                break
            except ValueError:
                continue
    if d is None:
        return None
    eta = reference.year - d.year - ((reference.month, reference.day) < (d.month, d.day))
    return eta if 0 < eta < 130 else None


def from_fiscal_code(cf: Any, reference: date) -> tuple[str, int] | None:
    """(sesso, età) da un codice fiscale di persona fisica; None se non valido."""
    if not isinstance(cf, str):
        return None
    m = CF_RE.match(cf.strip().upper())
    if not m:
        return None
    yy, mese, gg = int(m.group(1)), MESI_CF.find(m.group(2)) + 1, int(m.group(3))
    if mese == 0:
        return None
    donna = gg > 40
    giorno = gg - 40 if donna else gg
    if not 1 <= giorno <= 31:
        return None
    for secolo in (2000, 1900):
        try:
            nascita = date(secolo + yy, mese, giorno)
        except ValueError:
            continue
        eta = (
            reference.year
            - nascita.year
            - ((reference.month, reference.day) < (nascita.month, nascita.day))
        )
        if AGE_MIN <= eta <= AGE_MAX + 10:
            return ("f" if donna else "m", eta)
    return None


def sector_from_ateco(v: Any) -> str | None:
    digits = re.sub(r"\D", "", str(v)) if v is not None else ""
    if len(digits) < 2:
        return None
    return cl.SECTOR_BY_DIVISION.get(digits[:2])


def size_class_from_employees(v: Any) -> str | None:
    n = parse_int(v)
    if n is None or n == 0:
        return None
    for classe, (lo, hi) in cat.SIZE_CLASS_BOUNDS.items():
        if lo <= n <= hi:
            return classe
    return cat.SIZE_CLASS_LARGE


def unit_of(client_type: Any, vat: Any, fiscal_code: Any) -> str:
    n = _norm_value(client_type)
    if n in FIRM_TYPES:
        return "imprese"
    if n in INDIVIDUAL_TYPES:
        return "individui"
    if vat not in (None, "") and re.sub(r"\D", "", str(vat)):
        return "imprese"
    return "individui"


# --------------------------------------------------------------------------- #
# Lettura del file
# --------------------------------------------------------------------------- #


def read_table(path: Path, sheet: str | None = None) -> tuple[list[str], Iterator[list[Any]]]:
    """Intestazioni e righe (liste) di un CSV o di un foglio Excel."""
    if not path.is_file():
        raise ContactsError(f"file di anagrafiche non trovato: {path}")
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(str(path), read_only=True, data_only=True)
        ws = wb[sheet] if sheet else wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        header: list[str] | None = None
        for r in rows:
            if r and sum(1 for c in r if c not in (None, "")) >= 2:
                header = ["" if c is None else str(c).strip() for c in r]
                break
        if header is None:
            raise ContactsError("foglio senza intestazioni")
        return header, (list(r) for r in rows)
    if suffix in (".csv", ".txt"):
        testo = path.read_text(encoding="utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(testo[:4096], delimiters=";,\t|")
        reader = csv.reader(testo.splitlines(), dialect)
        header = [h.strip() for h in next(reader)]
        return header, (list(r) for r in reader)
    raise ContactsError(f"formato '{suffix}' non supportato: usare .xlsx o .csv")


def detect_columns(headers: list[str], mapping: dict[str, str] | None = None) -> dict[str, int]:
    """Indice di colonna per ogni campo canonico riconosciuto."""
    norm = [normalize_header(h) for h in headers]
    out: dict[str, int] = {}
    for campo, header in (mapping or {}).items():
        if campo not in CANONICAL:
            raise ContactsError(
                f"mapping: campo '{campo}' sconosciuto; ammessi {', '.join(CANONICAL)}"
            )
        if header not in headers:
            raise ContactsError(f"mapping: colonna '{header}' assente nel file")
        out[campo] = headers.index(header)
    for campo, sinonimi in SYNONYMS.items():
        if campo in out:
            continue
        for s in sinonimi:
            if s in norm:
                i = norm.index(s)
                if any(h in norm[i] for h in NEVER_READ_HINTS) and campo != "record_id":
                    continue
                out[campo] = i
                break
    return out


# --------------------------------------------------------------------------- #
# Risultato
# --------------------------------------------------------------------------- #

RECORD_COLUMNS: dict[str, Any] = {
    "row": pl.Int64,
    "record_id": pl.String,
    "unit": pl.String,
    "sex": pl.String,
    "age": pl.Int64,
    "age_band": pl.String,
    "region_code": pl.String,
    "region": pl.String,
    "macro_area": pl.String,
    "province": pl.String,
    "sector": pl.String,
    "size_class": pl.String,
    "employees": pl.Int64,
    "role": pl.String,
    "sex_known": pl.Boolean,
    "age_known": pl.Boolean,
    "sector_known": pl.Boolean,
    "size_known": pl.Boolean,
}


@dataclass
class ContactsResult:
    path: Path
    columns: dict[str, str]  # campo canonico -> intestazione usata
    records: pl.DataFrame
    rejected: list[tuple[int, str]] = field(default_factory=list)
    rows_read: int = 0
    duplicates: int = 0
    excluded_by_keep: int = 0
    excluded_by_unit: int = 0

    @property
    def n(self) -> int:
        return self.records.height

    def report(self) -> dict[str, Any]:
        motivi: dict[str, int] = {}
        for _r, m in self.rejected:
            motivi[m] = motivi.get(m, 0) + 1
        per_unit = dict(self.records.group_by("unit").len().iter_rows()) if self.n else {}
        return {
            "path": str(self.path),
            "columns": self.columns,
            "rows_read": self.rows_read,
            "excluded_by_keep": self.excluded_by_keep,
            "excluded_by_unit": self.excluded_by_unit,
            "duplicates": self.duplicates,
            "rejected": motivi,
            "valid": self.n,
            "by_unit": {str(k): int(v) for k, v in per_unit.items()},
            "known": {
                k: int(self.records[k].sum()) if self.n else 0
                for k in ("sex_known", "age_known", "sector_known", "size_known")
            },
        }


def _keep(row: list[Any], headers: list[str], keep: dict[str, list[str]] | None) -> bool:
    if not keep:
        return True
    for col, valori in keep.items():
        if col not in headers:
            raise ContactsError(f"keep: colonna '{col}' assente nel file")
        v = row[headers.index(col)]
        if _norm_value(v) not in {_norm_value(x) for x in valori}:
            return False
    return True


def load_contacts(
    path: Path,
    *,
    unit: str | None = None,
    sheet: str | None = None,
    mapping: dict[str, str] | None = None,
    keep: dict[str, list[str]] | None = None,
    reference: date | None = None,
) -> ContactsResult:
    """Legge l'anagrafica e restituisce i record utilizzabili, senza dati personali.

    L'unità di ogni riga (individuo o impresa) viene dalla tipologia cliente o
    dalla partita IVA; `unit` tiene solo le righe di quell'unità.
    """
    oggi = reference or date.today()
    headers, rows = read_table(path, sheet)
    cols = detect_columns(headers, mapping)
    if not any(c in cols for c in ("sex", "fiscal_code", "vat", "client_type", "age")):
        raise ContactsError(
            "nessuna colonna utile riconosciuta (sesso, codice fiscale, partita IVA, tipologia); "
            f"intestazioni trovate: {', '.join(h for h in headers if h)[:300]}"
        )
    province = load_provinces()
    result = ContactsResult(
        path=path,
        columns={c: headers[i] for c, i in cols.items()},
        records=pl.DataFrame(schema=RECORD_COLUMNS),
    )

    def get(row: list[Any], campo: str) -> Any:
        i = cols.get(campo)
        if i is None or i >= len(row):
            return None
        v = row[i]
        if v in ("",):
            return None
        # Excel legge gli identificativi numerici come float: "2866.0" -> "2866".
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        if isinstance(v, str) and re.fullmatch(r"\d+\.0+", v.strip()):
            return v.strip().split(".")[0]
        return v

    visti: set[str] = set()
    out: list[dict[str, Any]] = []
    for n_row, row in enumerate(rows, start=2):
        if not row or all(c in (None, "") for c in row):
            continue
        result.rows_read += 1
        if not _keep(row, headers, keep):
            result.excluded_by_keep += 1
            continue
        cf = get(row, "fiscal_code")
        vat = get(row, "vat")
        rid = get(row, "record_id")
        chiave = (
            str(rid)
            if rid is not None
            else (str(vat) if vat is not None else str(cf) if cf else None)
        )
        if chiave is not None:
            if chiave in visti:
                result.duplicates += 1
                continue
            visti.add(chiave)
        kind = unit_of(get(row, "client_type"), vat, cf)
        if unit is not None and kind != unit:
            result.excluded_by_unit += 1
            continue
        sex = parse_sex(get(row, "sex"))
        age = parse_age(get(row, "age"))
        if age is None:
            age = parse_birth_date(get(row, "birth_date"), oggi)
        da_cf = from_fiscal_code(cf, oggi)
        if da_cf is not None:
            sex = sex or da_cf[0]
            age = age if age is not None else da_cf[1]
        regione: str | None = None
        sigla: str | None = None
        if get(row, "region") is not None:
            regione = region_slug(get(row, "region"))
        if regione is None and get(row, "province") is not None:
            sigla = province.sigla(get(row, "province"))
            regione = province.region_of_sigla(sigla) if sigla else None
        if regione is None and get(row, "comune_code") is not None:
            trovato = province.region_of_comune_code(get(row, "comune_code"))
            if trovato:
                regione, sigla = trovato
        if regione is None:
            result.rejected.append((n_row, "territorio non riconosciuto"))
            continue
        sector = sector_from_ateco(get(row, "ateco"))
        employees = parse_int(get(row, "employees"))
        size_class = size_class_from_employees(employees) if employees is not None else None
        if kind == "individui":
            if sex is None:
                result.rejected.append((n_row, "sesso mancante"))
                continue
            if age is None or not AGE_MIN <= age <= AGE_MAX:
                result.rejected.append((n_row, "età mancante o fuori 18-100"))
                continue
        else:
            if size_class == cat.SIZE_CLASS_LARGE:
                result.rejected.append((n_row, "grande impresa, oltre 249 addetti"))
                continue
            if age is not None and not AGE_MIN <= age <= AGE_MAX:
                sex, age = None, None
        ruolo = get(row, "role")
        role = _norm_value(ruolo) if ruolo is not None else None
        if role is not None and role not in cat.RESPONDENT_ROLES:
            role = None
        out.append(
            {
                "row": n_row,
                "record_id": str(rid) if rid is not None else None,
                "unit": kind,
                "sex": sex,
                "age": age,
                "age_band": cl.age_band(age) if age is not None else None,
                "region_code": REGION_CODE_BY_SLUG[regione],
                "region": regione,
                "macro_area": MACRO_BY_SLUG[regione],
                "province": sigla,
                "sector": sector,
                "size_class": size_class,
                "employees": employees,
                "role": role,
                "sex_known": sex is not None,
                "age_known": age is not None,
                "sector_known": sector is not None,
                "size_known": size_class is not None,
            }
        )
    result.records = (
        pl.DataFrame(out, schema=RECORD_COLUMNS) if out else pl.DataFrame(schema=RECORD_COLUMNS)
    )
    return result


def profile_text(result: ContactsResult) -> str:
    """Riepilogo leggibile per la CLI e il rapporto di `prepare`."""
    r = result.report()
    righe = [
        f"Anagrafica: {r['path']}",
        f"Righe lette {r['rows_read']}, escluse dal filtro {r['excluded_by_keep']}, "
        f"di altra unità {r['excluded_by_unit']}, "
        f"duplicati {r['duplicates']}, scartate {sum(r['rejected'].values())}, valide {r['valid']}",
        "Colonne riconosciute: " + ", ".join(f"{k} <- {v}" for k, v in r["columns"].items()),
        "Per unità: " + ", ".join(f"{k}={v}" for k, v in r["by_unit"].items()),
        "Attributi noti dal file: "
        + ", ".join(f"{k.removesuffix('_known')}={v}" for k, v in r["known"].items()),
    ]
    if r["rejected"]:
        righe.append("Motivi di scarto: " + ", ".join(f"{k}={v}" for k, v in r["rejected"].items()))
    return "\n".join(righe)


def iter_rejected(result: ContactsResult) -> Iterable[str]:
    for row, motivo in result.rejected:
        yield f"riga {row}: {motivo}"
