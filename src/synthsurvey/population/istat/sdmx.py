"""Client minimale per l'API SDMX REST di ISTAT (esploradati.istat.it).

Scarica dati in formato CSV SDMX e li conserva in una cache su disco
indicizzata per hash dell'URL: la stessa richiesta non tocca più la rete,
e in modalità offline il client legge solo dalla cache.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

SDMX_BASE_URL = "https://esploradati.istat.it/SDMXWS/rest"
AGENCY = "IT1"
CSV_ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0"


class SdmxError(Exception):
    """Errore di rete, di risposta o cache mancante in modalità offline."""


@dataclass(frozen=True)
class RawResponse:
    """Risposta grezza, salvata su disco insieme ai suoi metadati."""

    url: str
    path: Path
    sha256: str
    fetched_at: str
    from_cache: bool
    text: str


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class SdmxClient:
    def __init__(
        self,
        raw_dir: Path,
        *,
        base_url: str = SDMX_BASE_URL,
        offline: bool = False,
        timeout_s: float = 300.0,
        retries: int = 3,
        backoff_s: float = 2.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.base_url = base_url.rstrip("/")
        self.offline = offline
        self.timeout_s = timeout_s
        self.retries = max(1, retries)
        self.backoff_s = backoff_s
        self._transport = transport

    def data_url(
        self, dataflow: str, key: str, start: str | None = None, end: str | None = None
    ) -> str:
        url = f"{self.base_url}/data/{dataflow}/{key}"
        params = []
        if start:
            params.append(f"startPeriod={start}")
        if end:
            params.append(f"endPeriod={end}")
        return url + ("?" + "&".join(params) if params else "")

    def _cache_paths(self, dataflow: str, url: str) -> tuple[Path, Path]:
        stem = sha256_text(url)[:16]
        folder = self.raw_dir / dataflow
        return folder / f"{stem}.csv", folder / f"{stem}.meta.json"

    def fetch_csv(
        self, dataflow: str, key: str, start: str | None = None, end: str | None = None
    ) -> RawResponse:
        url = self.data_url(dataflow, key, start, end)
        csv_path, meta_path = self._cache_paths(dataflow, url)
        if csv_path.is_file() and meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            text = csv_path.read_bytes().decode("utf-8")
            return RawResponse(
                url=url,
                path=csv_path,
                sha256=sha256_text(text),
                fetched_at=meta["fetched_at"],
                from_cache=True,
                text=text,
            )
        if self.offline:
            raise SdmxError(f"modalità offline e nessuna copia in cache per {url}")

        text = self._download(url)
        fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_bytes(text.encode("utf-8"))  # byte esatti: l'hash deve coincidere
        meta_path.write_text(
            json.dumps({"url": url, "fetched_at": fetched_at}, indent=2), encoding="utf-8"
        )
        return RawResponse(
            url=url,
            path=csv_path,
            sha256=sha256_text(text),
            fetched_at=fetched_at,
            from_cache=False,
            text=text,
        )

    def _download(self, url: str) -> str:
        ultimo: Exception | None = None
        with httpx.Client(
            timeout=httpx.Timeout(self.timeout_s, connect=30.0),
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            for tentativo in range(self.retries):
                try:
                    r = client.get(url, headers={"Accept": CSV_ACCEPT})
                except httpx.TransportError as exc:
                    ultimo = exc
                else:
                    if r.status_code == 404:
                        raise SdmxError(f"nessun dato per {url} (404)")
                    if r.status_code < 500:
                        if r.status_code != 200:
                            raise SdmxError(f"risposta {r.status_code} per {url}")
                        if not r.text.startswith("DATAFLOW"):
                            raise SdmxError(f"risposta inattesa (non CSV SDMX) per {url}")
                        return r.text
                    ultimo = SdmxError(f"risposta {r.status_code} per {url}")
                if tentativo < self.retries - 1 and self.backoff_s > 0:
                    time.sleep(self.backoff_s * (2**tentativo))
        raise SdmxError(f"scaricamento fallito dopo {self.retries} tentativi: {ultimo}")
