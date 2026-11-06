"""Popolazione sintetica delle imprese: la tavola ASIA è già una congiunta esatta."""

import polars as pl

from synthsurvey.population.tables import IstatTables


def build_imprese(t: IstatTables) -> pl.DataFrame:
    """Celle regione x settore x classe di addetti con conteggio (`count`)."""
    return t.firms.filter(pl.col("count") > 0).sort(["region_code", "sector", "size_class"])
