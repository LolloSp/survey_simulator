"""Orchestrazione: scarica (o rilegge dalla cache), normalizza, scrive tavole e manifest."""

from dataclasses import dataclass
from pathlib import Path

from survey_simulator.population.istat.manifest import (
    Manifest,
    RawFile,
    TableEntry,
    now_iso,
    read_manifest,
    write_manifest,
)
from survey_simulator.population.istat.sdmx import SdmxClient, sha256_file
from survey_simulator.population.istat.tables import TableSpec


@dataclass(frozen=True)
class FetchResult:
    manifest_path: Path
    manifest: Manifest
    updated: list[str]


def fetch_table(client: SdmxClient, spec: TableSpec, processed_dir: Path) -> TableEntry:
    raws = [client.fetch_csv(r.dataflow, r.key, r.start, r.end) for r in spec.requests]
    df = spec.normalize([r.text for r in raws], spec.period)
    atteso = list(spec.columns)
    if df.columns != atteso:
        raise AssertionError(f"{spec.name}: colonne {df.columns} diverse da {atteso}")
    processed_dir.mkdir(parents=True, exist_ok=True)
    out = processed_dir / spec.filename
    df.write_csv(out)
    return TableEntry(
        name=spec.name,
        description=spec.description,
        source_name=spec.source_name,
        period=spec.period,
        file=spec.filename,
        sha256=sha256_file(out),
        rows=df.height,
        columns=atteso,
        raw=[
            RawFile(
                dataflow=req.dataflow,
                key=req.key,
                url=raw.url,
                file=raw.path.relative_to(client.raw_dir).as_posix(),
                sha256=raw.sha256,
                fetched_at=raw.fetched_at,
                from_cache=raw.from_cache,
            )
            for req, raw in zip(spec.requests, raws, strict=True)
        ],
        generated_at=now_iso(),
    )


def fetch_tables(client: SdmxClient, specs: list[TableSpec], processed_dir: Path) -> FetchResult:
    """Aggiorna le tavole indicate e il manifest, conservando le voci delle altre tavole."""
    processed_dir = Path(processed_dir)
    esistente = read_manifest(processed_dir)
    tables = dict(esistente.tables) if esistente else {}
    aggiornate: list[str] = []
    for spec in specs:
        tables[spec.name] = fetch_table(client, spec, processed_dir)
        aggiornate.append(spec.name)
    manifest = Manifest(
        generated_at=now_iso(),
        sdmx_base_url=client.base_url,
        tables=dict(sorted(tables.items())),
    )
    path = write_manifest(processed_dir, manifest)
    return FetchResult(manifest_path=path, manifest=manifest, updated=aggiornate)
