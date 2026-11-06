"""Orchestrazione: tavole su disco, manifest con hash, rilettura dalla cache, verifica."""

import dataclasses
import functools
from pathlib import Path

import httpx
import polars as pl
import pytest

from synthsurvey.population.istat import (
    MANIFEST_NAME,
    TABLES,
    SdmxError,
    TableSpec,
    fetch_tables,
    read_manifest,
    tables_for_sources,
    verify_manifest,
)
from tests.population.conftest import REGIONI_FIXTURE, MakeClient


def specs_su_fixture() -> list[TableSpec]:
    """Le stesse tavole del registro, ma con il controllo regioni limitato alle fixture."""
    return [
        dataclasses.replace(
            spec, normalize=functools.partial(spec.normalize, required_regions=REGIONI_FIXTURE)
        )
        for spec in TABLES.values()
    ]


def test_tavole_per_sorgente() -> None:
    assert [t.name for t in tables_for_sources(["istat_imprese"])] == [
        "firms_region_sector_size",
        "firm_relations_sector_size",
        "firm_objectives_sector_size",
    ]
    tutte = tables_for_sources(["istat_individui", "istat_imprese", "istat_individui"])
    assert len(tutte) == len(TABLES)
    assert tables_for_sources(["ignota"]) == []


def test_fetch_scrive_tavole_e_manifest(
    make_client: MakeClient,
    tmp_path: Path,
    fixture_transport: tuple[httpx.MockTransport, list[str]],
) -> None:
    _, chiamate = fixture_transport
    processed = tmp_path / "processed"
    result = fetch_tables(make_client(), specs_su_fixture(), processed)

    assert result.manifest_path == processed / MANIFEST_NAME
    assert sorted(result.updated) == sorted(TABLES)
    # Richieste distinte: la stessa richiesta condivisa da due tavole va in cache.
    distinte = {(r.dataflow, r.key) for spec in TABLES.values() for r in spec.requests}
    assert len(chiamate) == len(distinte)
    for spec in TABLES.values():
        entry = result.manifest.tables[spec.name]
        assert (processed / entry.file).is_file()
        assert entry.columns == list(spec.columns)
        assert entry.period == spec.period
        assert entry.rows == pl.read_csv(processed / entry.file).height > 0
        # Solo la richiesta condivisa (internet, riusata dalla pratica religiosa) viene dalla cache.
        assert all(
            not r.from_cache or r.dataflow == "83_63_DF_DCCV_AVQ_PERSONE_236" for r in entry.raw
        )
        assert all(r.dataflow == q.dataflow for r, q in zip(entry.raw, spec.requests, strict=True))
    assert "ISTAT" in result.manifest.license["attribution"]
    assert verify_manifest(processed, tmp_path / "raw") == []


def test_seconda_esecuzione_dalla_cache_anche_offline(
    make_client: MakeClient, tmp_path: Path
) -> None:
    processed = tmp_path / "processed"
    specs = specs_su_fixture()
    primo = fetch_tables(make_client(), specs, processed)
    secondo = fetch_tables(make_client(offline=True), specs, processed)
    for name in TABLES:
        assert all(r.from_cache for r in secondo.manifest.tables[name].raw)
        assert secondo.manifest.tables[name].sha256 == primo.manifest.tables[name].sha256
        assert [r.sha256 for r in secondo.manifest.tables[name].raw] == [
            r.sha256 for r in primo.manifest.tables[name].raw
        ]


def test_aggiornamento_parziale_conserva_le_altre_tavole(
    make_client: MakeClient, tmp_path: Path
) -> None:
    processed = tmp_path / "processed"
    specs = specs_su_fixture()
    fetch_tables(make_client(), specs, processed)
    solo_imprese = [s for s in specs if s.name == "firms_region_sector_size"]
    result = fetch_tables(make_client(), solo_imprese, processed)
    assert result.updated == ["firms_region_sector_size"]
    assert set(result.manifest.tables) == set(TABLES)
    assert list(result.manifest.tables) == sorted(TABLES), "ordine stabile nel manifest"


def test_verifica_rileva_modifiche(make_client: MakeClient, tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    fetch_tables(make_client(), specs_su_fixture(), processed)
    assert verify_manifest(processed, tmp_path / "raw") == []

    file = processed / "firms_region_sector_size.csv"
    file.write_text(
        file.read_text(encoding="utf-8") + "ITC1,piemonte,nord_ovest,commercio,micro,1\n"
    )
    problemi = verify_manifest(processed, tmp_path / "raw")
    assert problemi == [
        "firms_region_sector_size: hash di firms_region_sector_size.csv diverso dal manifest"
    ]

    file.unlink()
    assert verify_manifest(processed) == [
        "firms_region_sector_size: file firms_region_sector_size.csv mancante"
    ]


def test_verifica_file_grezzo_modificato(make_client: MakeClient, tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    manifest = fetch_tables(make_client(), specs_su_fixture(), processed).manifest
    raw_file = tmp_path / "raw" / manifest.tables["education_sex_ageclass_national"].raw[0].file
    raw_file.write_text(raw_file.read_text(encoding="utf-8") + "\n")
    problemi = verify_manifest(processed, tmp_path / "raw")
    assert len(problemi) == 1
    assert problemi[0].startswith("education_sex_ageclass_national: hash del file grezzo")
    # Senza la cartella dei grezzi la verifica guarda solo le tavole normalizzate.
    assert verify_manifest(processed) == []


def test_manifest_assente(tmp_path: Path) -> None:
    assert read_manifest(tmp_path) is None
    assert verify_manifest(tmp_path) == [f"manifest non trovato in {tmp_path}"]


def test_offline_senza_cache(make_client: MakeClient, tmp_path: Path) -> None:
    with pytest.raises(SdmxError, match="offline"):
        fetch_tables(make_client(offline=True), specs_su_fixture()[:1], tmp_path / "processed")
