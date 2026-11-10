"""Estrazione reale dall'API ISTAT (opzionale: `pytest --network`).

Scarica la tavola più piccola in una cartella temporanea e confronta il
risultato normalizzato con quello versionato in data/processed: se i due
hash coincidono, l'API risponde ancora come al momento del manifest e la
pipeline è riproducibile. Se ISTAT rivede i dati il test fallisce: è il
segnale per rilanciare `survey-simulator data fetch` e aggiornare il manifest.
"""

from pathlib import Path

import pytest

from survey_simulator.population.istat import TABLES, SdmxClient, fetch_tables, read_manifest

PROCESSED = Path(__file__).resolve().parents[3] / "data" / "processed"
TAVOLA = "education_sex_ageclass_national"

pytestmark = pytest.mark.network


def test_estrazione_reale_riproduce_la_tavola_versionata(tmp_path: Path) -> None:
    manifest = read_manifest(PROCESSED)
    assert manifest is not None
    atteso = manifest.tables[TAVOLA]

    client = SdmxClient(tmp_path / "raw")
    result = fetch_tables(client, [TABLES[TAVOLA]], tmp_path / "processed")
    ottenuto = result.manifest.tables[TAVOLA]

    assert all(not r.from_cache for r in ottenuto.raw), "deve passare dalla rete"
    assert ottenuto.rows == atteso.rows
    assert ottenuto.sha256 == atteso.sha256, (
        "la tavola normalizzata dall'API differisce da data/processed: "
        "ISTAT ha rivisto i dati o il dataflow è cambiato; rilanciare `survey-simulator data fetch`"
    )
