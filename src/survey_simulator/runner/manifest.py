"""Manifest del run e congelamento.

Il manifest registra tutto ciò che serve a riprodurre o confrontare un run:
configurazione completa, hash del questionario, delle tavole ISTAT, dei
prompt e dei priori, modelli, versione del pacchetto, piano, statistiche.
Congelare un run significa calcolare l'hash di ogni file della cartella e
scriverlo nel manifest con `frozen: true`: da quel momento nessun comando
scrive più nella cartella e `verify_frozen` rileva qualsiasi modifica.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_NAME = "manifest.json"


class FrozenError(Exception):
    """Tentativo di modificare un run congelato."""


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for blocco in iter(lambda: fh.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def manifest_path(run_dir: Path) -> Path:
    return run_dir / MANIFEST_NAME


def read_manifest(run_dir: Path) -> dict[str, Any] | None:
    path = manifest_path(run_dir)
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def write_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    esistente = read_manifest(run_dir)
    if esistente is not None and esistente.get("frozen"):
        raise FrozenError(f"run congelato: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_path(run_dir)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def is_frozen(run_dir: Path) -> bool:
    m = read_manifest(run_dir)
    return bool(m and m.get("frozen"))


def assert_writable(run_dir: Path) -> None:
    if is_frozen(run_dir):
        raise FrozenError(f"run congelato, nessuna modifica ammessa: {run_dir}")


def file_hashes(run_dir: Path) -> dict[str, str]:
    """Hash di tutti i file della cartella del run, manifest escluso, in ordine stabile."""
    out: dict[str, str] = {}
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != MANIFEST_NAME:
            out[path.relative_to(run_dir).as_posix()] = sha256_file(path)
    return out


def freeze_run(run_dir: Path) -> dict[str, Any]:
    """Congela il run: hash dei file nel manifest, `frozen: true`. Idempotente."""
    manifest = read_manifest(run_dir)
    if manifest is None:
        raise FileNotFoundError(f"manifest assente in {run_dir}")
    if manifest.get("frozen"):
        return manifest
    manifest["files"] = file_hashes(run_dir)
    manifest["frozen"] = True
    manifest["frozen_at"] = now_iso()
    manifest["manifest_sha256_before_freeze"] = hashlib.sha256(
        json.dumps(
            {k: v for k, v in manifest.items() if k not in ("files", "frozen", "frozen_at")},
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    write_manifest(run_dir, manifest)
    return manifest


def verify_frozen(run_dir: Path) -> list[str]:
    """Differenze fra i file attuali e gli hash registrati al congelamento."""
    manifest = read_manifest(run_dir)
    if manifest is None or not manifest.get("frozen"):
        return ["il run non è congelato"]
    attesi: dict[str, str] = manifest.get("files", {})
    attuali = file_hashes(run_dir)
    problemi = []
    for nome, h in attesi.items():
        if nome not in attuali:
            problemi.append(f"file mancante: {nome}")
        elif attuali[nome] != h:
            problemi.append(f"file modificato: {nome}")
    for nome in attuali:
        if nome not in attesi:
            problemi.append(f"file aggiunto: {nome}")
    return problemi
