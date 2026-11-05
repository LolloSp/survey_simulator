"""Fixture condivise: estratti reali delle risposte SDMX (ITC1, ITG2, IT) e client finto."""

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from synthsurvey.population.istat import SdmxClient

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REGIONI_FIXTURE: tuple[str, ...] = ("ITC1", "ITG2")


def fixture_text(dataflow: str) -> str:
    return (FIXTURES / f"{dataflow}.csv").read_text(encoding="utf-8")


def dataflow_from_url(url: str) -> str:
    # .../rest/data/<dataflow>/<key>?...
    return url.split("/data/", 1)[1].split("/", 1)[0]


@pytest.fixture
def fixture_transport() -> tuple[httpx.MockTransport, list[str]]:
    """Trasporto httpx che risponde con la fixture del dataflow richiesto e registra le chiamate."""
    chiamate: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        chiamate.append(url)
        try:
            return httpx.Response(200, text=fixture_text(dataflow_from_url(url)))
        except FileNotFoundError:
            return httpx.Response(404, text="not found")

    return httpx.MockTransport(handler), chiamate


MakeClient = Callable[..., SdmxClient]


@pytest.fixture
def make_client(
    tmp_path: Path, fixture_transport: tuple[httpx.MockTransport, list[str]]
) -> MakeClient:
    transport, _ = fixture_transport

    def _make(**kwargs: object) -> SdmxClient:
        opts: dict[str, object] = {"transport": transport, "backoff_s": 0.0}
        opts.update(kwargs)
        return SdmxClient(tmp_path / "raw", **opts)  # type: ignore[arg-type]

    return _make
