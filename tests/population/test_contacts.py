"""Anagrafiche (M13): riconoscimento colonne, derivazioni, scarti, campione e persone."""

import csv
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from openpyxl import Workbook

from survey_simulator.config import load_config
from survey_simulator.personas import build_personas
from survey_simulator.personas.schema import Provenance
from survey_simulator.population.contacts import (
    ContactsError,
    detect_columns,
    from_fiscal_code,
    load_contacts,
    load_provinces,
    parse_birth_date,
    parse_sex,
    profile_text,
    region_slug,
    sector_from_ateco,
    size_class_from_employees,
    unit_of,
)
from survey_simulator.population.sample import build_sample
from survey_simulator.population.tables import IstatTables, load_tables
from tests.config.conftest import ESEMPI_DIR

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
QUESTIONARIO = ESEMPI_DIR.parent.parent / "questionnaires" / "examples" / "mercato_v1.yaml"
OGGI = date(2026, 11, 8)

# Codici fiscali sintattici (persone inventate): anno, mese, giorno (+40 donne).
CF_UOMO_1980 = "RSSMRA80A01H501U"  # 1 gennaio 1980, uomo
CF_DONNA_1995 = "BNCLRA95E45F205Z"  # 5 maggio 1995, donna
CF_DONNA_1950 = "VRDGPP50T70L219K"  # 30 dicembre 1950, donna
CF_MINORE = "RSSMRA10A01H501U"  # 2010: minorenne

RIGHE: list[dict[str, Any]] = [
    # Tipologia, CF, sesso, provincia/comune, P.IVA, ATECO, addetti
    {
        "CodiceCliente": 1001.0,
        "Tipo cliente": "C",
        "Codice Fiscale": CF_UOMO_1980,
        "Sesso": "M",
        "Prov": "GE",
        "ISTATComune": "010025",
        "Nome": "X",
        "Email": "x@y.z",
    },
    {
        "CodiceCliente": 1002.0,
        "Tipo cliente": "C",
        "Codice Fiscale": CF_DONNA_1995,
        "Sesso": "",
        "Prov": "",
        "ISTATComune": "015146",
        "Nome": "Y",
        "Email": "y@y.z",
    },
    {
        "CodiceCliente": 1002.0,
        "Tipo cliente": "C",
        "Codice Fiscale": CF_DONNA_1995,
        "Sesso": "F",
        "Prov": "MI",
        "ISTATComune": "015146",
        "Nome": "Y",
        "Email": "y@y.z",
    },
    {
        "CodiceCliente": 1003.0,
        "Tipo cliente": "B",
        "Codice Fiscale": "",
        "Sesso": "",
        "Prov": "Torino",
        "ISTATComune": "",
        "Partita IVA": "01234567890",
        "Codice Ateco": "47.11.20",
        "Addetti": 12,
    },
    {
        "CodiceCliente": 1004.0,
        "Tipo cliente": "B",
        "Codice Fiscale": CF_DONNA_1950,
        "Sesso": "",
        "Prov": "BZ",
        "ISTATComune": "",
        "Partita IVA": "09876543210",
        "Codice Ateco": "97.00.00",
        "Addetti": "",
    },
    {
        "CodiceCliente": 1005.0,
        "Tipo cliente": "C",
        "Codice Fiscale": CF_MINORE,
        "Sesso": "M",
        "Prov": "RM",
        "ISTATComune": "",
    },
    {
        "CodiceCliente": 1006.0,
        "Tipo cliente": "C",
        "Codice Fiscale": "",
        "Sesso": "F",
        "Prov": "XX",
        "ISTATComune": "",
    },
    {
        "CodiceCliente": 1007.0,
        "Tipo cliente": "B",
        "Codice Fiscale": "",
        "Sesso": "",
        "Prov": "NA",
        "ISTATComune": "",
        "Partita IVA": "11111111111",
        "Codice Ateco": "10.11",
        "Addetti": 300,
    },
    {
        "CodiceCliente": 1008.0,
        "Tipo cliente": "C",
        "Codice Fiscale": "",
        "Sesso": "M",
        "Prov": "",
        "ISTATComune": "",
        "Regione": "Emilia-Romagna",
        "Età": 44,
    },
]
INTESTAZIONI = [
    "CodiceCliente",
    "Tipo cliente",
    "Codice Fiscale",
    "Nome",
    "Email",
    "Sesso",
    "Età",
    "Regione",
    "Prov",
    "ISTATComune",
    "Partita IVA",
    "Codice Ateco",
    "Addetti",
]


def scrivi_xlsx(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(INTESTAZIONI)
    for r in RIGHE:
        ws.append([r.get(h, "") for h in INTESTAZIONI])
    wb.save(str(path))
    return path


def scrivi_csv(path: Path) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(INTESTAZIONI)
        for r in RIGHE:
            w.writerow([r.get(h, "") for h in INTESTAZIONI])
    return path


@pytest.fixture(scope="session")
def tables() -> IstatTables:
    return load_tables(PROCESSED)


def test_derivazioni_elementari() -> None:
    assert from_fiscal_code(CF_UOMO_1980, OGGI) == ("m", 46)
    assert from_fiscal_code(CF_DONNA_1995, OGGI) == ("f", 31)
    assert from_fiscal_code(CF_DONNA_1950, OGGI) == ("f", 75)
    assert from_fiscal_code("non un cf", OGGI) is None and from_fiscal_code(None, OGGI) is None
    assert parse_sex("Femmina") == "f" and parse_sex("1") == "m" and parse_sex("?") is None
    assert parse_birth_date("01/01/1980", OGGI) == 46 and parse_birth_date("boh", OGGI) is None
    assert region_slug("Emilia-Romagna") == "emilia_romagna" and region_slug("Friuli") == (
        "friuli_venezia_giulia"
    )
    assert region_slug("Atlantide") is None
    assert sector_from_ateco("47.11.20") == "commercio" and sector_from_ateco("") is None
    assert size_class_from_employees(12) == "piccola" and size_class_from_employees(300) == (
        "grande"
    )
    assert unit_of("B", None, None) == "imprese" and unit_of("privato", None, None) == "individui"
    assert unit_of(None, "0123", None) == "imprese" and unit_of(None, None, "CF") == "individui"


def test_province() -> None:
    p = load_provinces()
    assert p.sigla("GE") == "GE" and p.sigla("Torino") == "TO" and p.sigla("ROMA") == "RM"
    assert p.sigla("Forlì") == "FC" and p.sigla("XX") is None
    assert p.region_of_sigla("BZ") == "trentino_alto_adige"
    assert p.region_of_comune_code("015146") == ("lombardia", "MI")
    assert p.region_of_comune_code("1272") == ("piemonte", "TO"), "codice senza zeri iniziali"
    assert p.region_of_comune_code("104001") == ("sardegna", "SS"), "provincia soppressa"
    assert p.region_of_comune_code("999999") is None
    assert len(p.by_sigla) == 107


def test_riconoscimento_colonne() -> None:
    cols = detect_columns(INTESTAZIONI)
    assert INTESTAZIONI[cols["record_id"]] == "CodiceCliente"
    assert INTESTAZIONI[cols["client_type"]] == "Tipo cliente"
    assert INTESTAZIONI[cols["fiscal_code"]] == "Codice Fiscale"
    assert INTESTAZIONI[cols["province"]] == "Prov" and INTESTAZIONI[cols["age"]] == "Età"
    assert INTESTAZIONI[cols["comune_code"]] == "ISTATComune"
    assert "Nome" not in {INTESTAZIONI[i] for i in cols.values()}, "i nomi non si leggono mai"
    override = detect_columns(INTESTAZIONI, {"sex": "Tipo cliente"})
    assert INTESTAZIONI[override["sex"]] == "Tipo cliente"
    with pytest.raises(ContactsError, match="sconosciuto"):
        detect_columns(INTESTAZIONI, {"nome": "Nome"})
    with pytest.raises(ContactsError, match="assente"):
        detect_columns(INTESTAZIONI, {"sex": "Genere"})


def test_caricamento_xlsx_e_csv(tmp_path: Path) -> None:
    xlsx = load_contacts(scrivi_xlsx(tmp_path / "a.xlsx"), reference=OGGI)
    csv_ = load_contacts(scrivi_csv(tmp_path / "a.csv"), reference=OGGI)
    for res in (xlsx, csv_):
        r = res.report()
        assert r["rows_read"] == 9 and r["duplicates"] == 1 and r["valid"] == 5
        assert r["rejected"] == {
            "età mancante o fuori 18-100": 1,
            "territorio non riconosciuto": 1,
            "grande impresa, oltre 249 addetti": 1,
        }
        assert r["by_unit"] == {"individui": 3, "imprese": 2}
        rec = {row["record_id"]: row for row in res.records.to_dicts()}
        assert set(rec) == {"1001", "1002", "1003", "1004", "1008"}
        assert rec["1001"]["sex"] == "m" and rec["1001"]["age"] == 46
        assert rec["1001"]["region"] == "liguria" and rec["1001"]["province"] == "GE"
        assert rec["1002"]["sex"] == "f" and rec["1002"]["region"] == "lombardia", (
            "dal CF e dal comune"
        )
        assert rec["1003"]["unit"] == "imprese" and rec["1003"]["sector"] == "commercio"
        assert rec["1003"]["size_class"] == "piccola" and rec["1003"]["sex"] is None
        assert rec["1004"]["sex"] == "f" and rec["1004"]["age"] == 75, "ditta con CF di persona"
        assert rec["1004"]["sector"] is None and rec["1004"]["size_known"] is False
        assert rec["1008"]["age"] == 44 and rec["1008"]["region"] == "emilia_romagna"
        for colonna in res.records.columns:
            assert colonna not in ("name", "fiscal_code", "email")
    assert "Colonne riconosciute" in profile_text(xlsx) and "scartate 3" in profile_text(xlsx)


def test_filtri_unita_keep_e_mapping(tmp_path: Path) -> None:
    path = scrivi_xlsx(tmp_path / "a.xlsx")
    privati = load_contacts(path, unit="individui", reference=OGGI)
    assert privati.n == 3 and privati.excluded_by_unit == 3
    imprese = load_contacts(path, unit="imprese", reference=OGGI)
    assert imprese.n == 2
    keep = load_contacts(path, keep={"Tipo cliente": ["B"]}, reference=OGGI)
    assert keep.n == 2 and keep.excluded_by_keep == 6
    with pytest.raises(ContactsError, match="keep"):
        load_contacts(path, keep={"Inesistente": ["x"]}, reference=OGGI)
    mappato = load_contacts(path, mapping={"age": "Addetti"}, reference=OGGI)
    assert mappato.columns["age"] == "Addetti"


def test_errori(tmp_path: Path) -> None:
    with pytest.raises(ContactsError, match="non trovato"):
        load_contacts(tmp_path / "manca.xlsx")
    (tmp_path / "x.odt").write_text("x", encoding="utf-8")
    with pytest.raises(ContactsError, match="non supportato"):
        load_contacts(tmp_path / "x.odt")
    inutile = tmp_path / "inutile.csv"
    inutile.write_text("a;b\n1;2\n", encoding="utf-8")
    with pytest.raises(ContactsError, match="nessuna colonna utile"):
        load_contacts(inutile)


def _config(tmp_path: Path, anagrafica: Path, **extra: Any) -> Path:
    raw = yaml.safe_load((ESEMPI_DIR / "mercato_100.yaml").read_text(encoding="utf-8"))
    raw["project"]["name"] = "anagrafica-test"
    raw["sample"] = {
        "total": None,
        "segments": {
            "consumer": {
                "source": "lista_clienti",
                "contacts": {"path": str(anagrafica), "unit": "individui"},
            },
            "pmi": {
                "source": "lista_clienti",
                "contacts": {"path": str(anagrafica), "unit": "imprese"},
                "respondent_role": ["titolare", "amministratore"],
            },
        },
    }
    raw["engine"]["models"] = [{"provider": "fake", "model": "fake-1"}]
    raw["questionnaire"]["path"] = str(QUESTIONARIO)
    raw["output"]["dir"] = str(tmp_path / "runs")
    for k, v in extra.items():
        raw[k].update(v)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path


def test_campione_e_persone_dalle_anagrafiche(tmp_path: Path, tables: IstatTables) -> None:
    anagrafica = scrivi_xlsx(tmp_path / "a.xlsx")
    loaded = load_config(_config(tmp_path, anagrafica))
    assert loaded.warnings == []
    sample = build_sample(loaded.config, PROCESSED, tables=tables)
    u = sample.units
    assert u.height == 5 and Counter(u["unit_kind"].to_list()) == {"individui": 3, "imprese": 2}
    assert set(u["weight"].to_list()) == {1.0} and set(u["source"].to_list()) == {"lista_clienti"}
    individui = u.filter(u["unit_kind"] == "individui")
    assert individui["education"].null_count() == 0 and individui["employment"].null_count() == 0
    imprese = u.filter(u["unit_kind"] == "imprese")
    assert imprese["sector"].null_count() == 0 and imprese["size_class"].null_count() == 0
    assert sample.private_map is not None and sample.private_map.height == 5
    assert set(sample.private_map["record_id"].to_list()) == {
        "1001",
        "1002",
        "1008",
        "1003",
        "1004",
    }
    assert sample.segments["pmi"].weights.summary()["max"] == 1.0
    # Riproducibile dal seed.
    di_nuovo = build_sample(loaded.config, PROCESSED, tables=tables)
    assert di_nuovo.units.equals(u)

    res = build_personas(sample, loaded.config, tables, processed_dir=PROCESSED)
    assert len(res.personas) == 5
    persone = {p.unit_id: p for p in res.personas}
    p1 = next(
        p for p in res.personas if p.provenance.get("sex") is Provenance.ANAGRAFICA and not p.firm
    )
    assert (
        p1.provenance["education"] is Provenance.ISTAT
        and p1.provenance["region"] is Provenance.ANAGRAFICA
    )
    ditta = next(p for p in res.personas if p.firm and p.age == 75)
    assert ditta.sex == "f" and ditta.provenance["sex"] is Provenance.ANAGRAFICA
    assert ditta.provenance["sector"] is Provenance.ISTAT, "ATECO 97 non mappato: settore da ISTAT"
    negozio = next(p for p in res.personas if p.firm and p.firm.size_class == "piccola")
    assert negozio.provenance["sector"] is Provenance.ANAGRAFICA
    assert negozio.provenance["size_class"] is Provenance.ANAGRAFICA
    assert negozio.provenance["sex"] is Provenance.IPOTESI, "senza CF il rispondente è ipotetico"
    assert all(p.name not in ("X", "Y") for p in res.personas), "nomi sintetici, mai dal file"
    assert "consumer_00001" in persone


def test_sottocampione_e_pilota(tmp_path: Path, tables: IstatTables) -> None:
    anagrafica = scrivi_xlsx(tmp_path / "a.xlsx")
    loaded = load_config(_config(tmp_path, anagrafica))
    pilota = build_sample(loaded.config, PROCESSED, n_total=3, tables=tables)
    assert pilota.units.height == 3
    assert any("sottocampione" in w for w in pilota.warnings)
    raw = yaml.safe_load(loaded.path.read_text(encoding="utf-8"))
    raw["sample"]["segments"]["consumer"]["size"] = 2
    loaded.path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    ridotto = build_sample(load_config(loaded.path).config, PROCESSED, tables=tables)
    assert ridotto.segments["consumer"].n == 2 and ridotto.segments["pmi"].n == 2


def test_regole_config_anagrafiche(tmp_path: Path) -> None:
    anagrafica = scrivi_xlsx(tmp_path / "a.xlsx")
    path = _config(tmp_path, anagrafica)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["sample"]["total"] = 100
    raw["sample"]["segments"]["consumer"]["share"] = 0.5
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    from survey_simulator.config import ConfigError

    with pytest.raises(ConfigError) as info:
        load_config(path)
    testo = str(info.value)
    assert "share" in testo and "non ammessa con lista_clienti" in testo
    raw["sample"]["segments"]["consumer"].pop("share")
    raw["sample"]["segments"]["pmi"] = {
        "source": "istat_imprese",
        "share": 1.0,
        "quotas": ["size_class"],
    }
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigError, match="non mescolare"):
        load_config(path)
    raw["sample"]["segments"].pop("pmi")
    raw["sample"]["segments"]["consumer"].pop("contacts")
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigError, match="richiede il blocco contacts"):
        load_config(path)
