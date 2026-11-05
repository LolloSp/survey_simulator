"""Estrazione e normalizzazione delle tavole ISTAT via API SDMX."""

from synthsurvey.population.istat.fetch import FetchResult, fetch_tables
from synthsurvey.population.istat.manifest import (
    MANIFEST_NAME,
    Manifest,
    TableEntry,
    read_manifest,
    verify_manifest,
    write_manifest,
)
from synthsurvey.population.istat.sdmx import SDMX_BASE_URL, RawResponse, SdmxClient, SdmxError
from synthsurvey.population.istat.tables import TABLES, TableSpec, tables_for_sources

__all__ = [
    "MANIFEST_NAME",
    "SDMX_BASE_URL",
    "TABLES",
    "FetchResult",
    "Manifest",
    "RawResponse",
    "SdmxClient",
    "SdmxError",
    "TableEntry",
    "TableSpec",
    "fetch_tables",
    "read_manifest",
    "tables_for_sources",
    "verify_manifest",
    "write_manifest",
]
