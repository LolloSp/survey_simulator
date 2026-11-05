"""Manifest delle tavole normalizzate: provenienza, periodo, hash, licenza."""

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from synthsurvey.population.istat.sdmx import sha256_file

MANIFEST_NAME = "manifest.json"

LICENSE = {
    "name": "Creative Commons Attribuzione 3.0 Italia (CC BY 3.0 IT)",
    "url": "https://creativecommons.org/licenses/by/3.0/it/",
    "attribution": "Fonte: ISTAT (www.istat.it), elaborazione synthsurvey",
    "note": (
        "I dati aggregati pubblicati da ISTAT possono essere riprodotti, distribuiti e "
        "adattati anche per fini commerciali citando la fonte."
    ),
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RawFile(StrictModel):
    dataflow: str
    key: str
    url: str
    file: str  # percorso relativo a data/raw
    sha256: str
    fetched_at: str
    from_cache: bool


class TableEntry(StrictModel):
    name: str
    description: str
    source_name: str
    period: str
    file: str  # nome del file in data/processed
    sha256: str
    rows: int
    columns: list[str]
    raw: list[RawFile]
    generated_at: str


class Manifest(StrictModel):
    version: int = 1
    generated_at: str
    sdmx_base_url: str
    license: dict[str, str] = Field(default_factory=lambda: dict(LICENSE))
    tables: dict[str, TableEntry] = Field(default_factory=dict)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def read_manifest(processed_dir: Path) -> Manifest | None:
    path = Path(processed_dir) / MANIFEST_NAME
    if not path.is_file():
        return None
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def write_manifest(processed_dir: Path, manifest: Manifest) -> Path:
    path = Path(processed_dir) / MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def verify_manifest(processed_dir: Path, raw_dir: Path | None = None) -> list[str]:
    """Ricalcola gli hash dei file e restituisce l'elenco dei problemi (vuoto se tutto torna).

    I file grezzi non sono versionati: se mancano non è un errore, se ci sono
    devono avere l'hash registrato.
    """
    processed_dir = Path(processed_dir)
    manifest = read_manifest(processed_dir)
    if manifest is None:
        return [f"manifest non trovato in {processed_dir}"]
    problemi: list[str] = []
    for name, entry in manifest.tables.items():
        path = processed_dir / entry.file
        if not path.is_file():
            problemi.append(f"{name}: file {entry.file} mancante")
            continue
        h = sha256_file(path)
        if h != entry.sha256:
            problemi.append(f"{name}: hash di {entry.file} diverso dal manifest")
        if raw_dir is not None:
            for raw in entry.raw:
                rp = Path(raw_dir) / raw.file
                if rp.is_file() and sha256_file(rp) != raw.sha256:
                    problemi.append(f"{name}: hash del file grezzo {raw.file} diverso dal manifest")
    return problemi
