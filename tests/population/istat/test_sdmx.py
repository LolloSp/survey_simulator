"""Client SDMX: cache su disco, modalità offline, errori e retry. Nessuna chiamata reale."""

from pathlib import Path

import httpx
import pytest

from survey_simulator.population.istat import SdmxClient, SdmxError
from tests.population.conftest import MakeClient

FLOW = "22_289_DF_DCIS_POPRES1_1"
KEY = "A.ITC1.JAN.1+2..99"


def test_url_dati() -> None:
    c = SdmxClient(Path("x"), base_url="https://host/rest/")
    assert c.data_url("F", "A.B") == "https://host/rest/data/F/A.B"
    assert c.data_url("F", "A.B", "2024", "2024") == (
        "https://host/rest/data/F/A.B?startPeriod=2024&endPeriod=2024"
    )


def test_scarica_e_mette_in_cache(
    make_client: MakeClient, fixture_transport: tuple[httpx.MockTransport, list[str]]
) -> None:
    _, chiamate = fixture_transport
    client = make_client()
    primo = client.fetch_csv(FLOW, KEY, "2025", "2025")
    assert primo.from_cache is False
    assert primo.text.startswith("DATAFLOW")
    assert primo.path.is_file()
    assert (
        primo.path.with_suffix(".meta.json").exists()
        or (primo.path.parent / (primo.path.stem + ".meta.json")).exists()
    )
    assert len(chiamate) == 1

    secondo = client.fetch_csv(FLOW, KEY, "2025", "2025")
    assert secondo.from_cache is True
    assert secondo.sha256 == primo.sha256
    assert secondo.fetched_at == primo.fetched_at
    assert len(chiamate) == 1, "la seconda lettura non deve toccare la rete"


def test_offline_senza_cache_fallisce(make_client: MakeClient) -> None:
    client = make_client(offline=True)
    with pytest.raises(SdmxError, match="offline"):
        client.fetch_csv(FLOW, KEY)


def test_offline_con_cache_funziona(make_client: MakeClient) -> None:
    make_client().fetch_csv(FLOW, KEY)
    assert make_client(offline=True).fetch_csv(FLOW, KEY).from_cache is True


def test_404_e_errore_chiaro(make_client: MakeClient) -> None:
    with pytest.raises(SdmxError, match="404"):
        make_client().fetch_csv("FLUSSO_INESISTENTE", KEY)


def test_retry_su_errore_server(tmp_path: Path) -> None:
    tentativi = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tentativi
        tentativi += 1
        if tentativi < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, text="DATAFLOW,X\nIT1:F,1\n")

    client = SdmxClient(tmp_path, transport=httpx.MockTransport(handler), retries=3, backoff_s=0.0)
    assert client.fetch_csv("F", "A").text.startswith("DATAFLOW")
    assert tentativi == 3


def test_retry_esaurito(tmp_path: Path) -> None:
    client = SdmxClient(
        tmp_path,
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="x")),
        retries=2,
        backoff_s=0.0,
    )
    with pytest.raises(SdmxError, match="2 tentativi"):
        client.fetch_csv("F", "A")
    assert not any(tmp_path.rglob("*.csv")), "nessun file in cache dopo un fallimento"


def test_errore_di_trasporto_con_retry(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("rete assente")

    client = SdmxClient(tmp_path, transport=httpx.MockTransport(handler), retries=2, backoff_s=0.0)
    with pytest.raises(SdmxError, match="rete assente"):
        client.fetch_csv("F", "A")


def test_risposta_non_csv(tmp_path: Path) -> None:
    client = SdmxClient(
        tmp_path,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>no</html>")),
        backoff_s=0.0,
    )
    with pytest.raises(SdmxError, match="non CSV"):
        client.fetch_csv("F", "A")
