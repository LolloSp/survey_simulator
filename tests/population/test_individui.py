"""Congiunta degli individui: riproduce le tavole ISTAT e conserva le interazioni del seed."""

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from synthsurvey.population import individui as ind
from synthsurvey.population.imprese import build_imprese
from synthsurvey.population.tables import IstatTables, TablesError, load_tables

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"


@pytest.fixture(scope="module")
def tables() -> IstatTables:
    return load_tables(PROCESSED)


@pytest.fixture(scope="module")
def pop(tables: IstatTables) -> ind.IndividuiPopulation:
    return ind.build_individui(tables)


def test_load_tables_richiede_manifest(tmp_path: Path) -> None:
    with pytest.raises(TablesError, match="manifest"):
        load_tables(tmp_path)


def test_ipf_converge(pop: ind.IndividuiPopulation) -> None:
    assert pop.ipf.converged
    assert pop.ipf.iterations < 50
    assert pop.table.shape == ind.SHAPE
    # Oltre i 79 anni il seed esclude occupati e persone in cerca: celle a zero volute.
    i_occ, i_cerca = ind.EMPLOYMENT.index("occupato"), ind.EMPLOYMENT.index("in_cerca")
    anziani = [i for i, (_l, lo, _h) in enumerate(ind.AGE_GROUPS) if lo >= ind.NO_WORK_AGE]
    assert anziani == [12, 13]
    assert (pop.table[:, :, anziani, :, i_occ] == 0).all()
    assert (pop.table[:, :, anziani, :, i_cerca] == 0).all()
    resto = np.delete(pop.table, anziani, axis=2)
    assert (resto > 0).all(), "altrove nessuna cella vuota: ogni combinazione è possibile"
    pensionati = ind.EMPLOYMENT.index("pensionato")
    assert (pop.table[:, :, anziani, :, pensionati] > 0).all()


def test_totale_e_marginale_popolazione(pop: ind.IndividuiPopulation, tables: IstatTables) -> None:
    adulti = tables.population.filter(pl.col("age") >= 18)
    assert abs(pop.table.sum() - adulti["count"].sum()) < 1e-3
    # Regione x sesso x gruppo quinquennale esatto.
    frame = pop.to_frame()
    atteso = (
        adulti.with_columns(
            pl.col("age").map_elements(ind.age_group_of, return_dtype=pl.String).alias("age_group")
        )
        .group_by(["region_code", "sex", "age_group"])
        .agg(pl.col("count").sum().alias("atteso"))
    )
    got = frame.group_by(["region_code", "sex", "age_group"]).agg(pl.col("count").sum())
    cmp = got.join(atteso, on=["region_code", "sex", "age_group"])
    assert cmp.height == 20 * 2 * len(ind.AGE_GROUPS)
    assert ((cmp["count"] - cmp["atteso"]).abs() < 1e-6 * cmp["atteso"]).all()


def test_quote_censuarie_rispettate(pop: ind.IndividuiPopulation, tables: IstatTables) -> None:
    """Nella classe 25-49 (senza correzione per minorenni) le quote coincidono col censimento."""
    frame = pop.to_frame()
    gruppi_25_49 = [g for g, lo, _ in ind.AGE_GROUPS if 25 <= lo <= 49]
    got = (
        frame.filter(pl.col("age_group").is_in(gruppi_25_49))
        .group_by(["region_code", "sex", "education"])
        .agg(pl.col("count").sum())
        .with_columns(
            (pl.col("count") / pl.col("count").sum().over(["region_code", "sex"])).alias("quota")
        )
    )
    att = tables.education.filter(pl.col("age_class") == "25_49").with_columns(
        (pl.col("count") / pl.col("count").sum().over(["region_code", "sex"])).alias("attesa")
    )
    cmp = got.join(att, on=["region_code", "sex", "education"])
    assert cmp.height == 20 * 2 * 3
    assert ((cmp["quota"] - cmp["attesa"]).abs() < 1e-6).all()

    got_emp = (
        frame.filter(pl.col("age_group").is_in(gruppi_25_49))
        .group_by(["region_code", "sex", "employment"])
        .agg(pl.col("count").sum())
        .with_columns(
            (pl.col("count") / pl.col("count").sum().over(["region_code", "sex"])).alias("quota")
        )
    )
    att_emp = tables.employment.filter(pl.col("age_class") == "25_49").with_columns(
        (pl.col("count") / pl.col("count").sum().over(["region_code", "sex"])).alias("attesa")
    )
    cmp = got_emp.join(att_emp, on=["region_code", "sex", "employment"])
    assert ((cmp["quota"] - cmp["attesa"]).abs() < 1e-6).all()


def test_minorenni_scorporati_dai_18_24(pop: ind.IndividuiPopulation, tables: IstatTables) -> None:
    frame = pop.to_frame()
    q = (
        frame.filter(pl.col("age_group") == "18_24")
        .group_by("education")
        .agg(pl.col("count").sum())
        .with_columns((pl.col("count") / pl.col("count").sum()).alias("quota"))
    )
    fino_media = q.filter(pl.col("education") == "fino_media")["quota"].item()
    grezza = tables.education.filter(pl.col("age_class") == "9_24").with_columns(
        (pl.col("count") / pl.col("count").sum()).alias("quota")
    )
    grezza_fm = grezza.filter(pl.col("education") == "fino_media")["quota"].sum()
    assert fino_media < grezza_fm, "senza i 9-17enni la quota fino_media dei 18-24 scende"
    assert 0.2 < fino_media < 0.6


def test_gradiente_eta_e_associazione_dal_seed(pop: ind.IndividuiPopulation) -> None:
    frame = pop.to_frame()

    def quota(df: pl.DataFrame, col: str, cat: str) -> float:
        tot = df["count"].sum()
        return float(df.filter(pl.col(col) == cat)["count"].sum() / tot)

    giovani = frame.filter(pl.col("age_band") == "25_34")
    anziani = frame.filter(pl.col("age_band") == "55_64")
    assert quota(giovani, "education", "laurea_o_oltre") > quota(
        anziani, "education", "laurea_o_oltre"
    )
    # Dentro la stessa classe censuaria (25-49) il gradiente viene dal seed delle Forze di lavoro.
    g25 = frame.filter(pl.col("age_group") == "25_29")
    g45 = frame.filter(pl.col("age_group") == "45_49")
    assert quota(g25, "education", "laurea_o_oltre") > quota(g45, "education", "laurea_o_oltre")
    # Associazione istruzione-condizione: fra i 35-44enni i laureati sono più spesso occupati.
    adulti = frame.filter(pl.col("age_band") == "35_44")
    laureati = adulti.filter(pl.col("education") == "laurea_o_oltre")
    bassa = adulti.filter(pl.col("education") == "fino_media")
    assert quota(laureati, "employment", "occupato") > quota(bassa, "employment", "occupato")


def test_frame_e_helper(pop: ind.IndividuiPopulation) -> None:
    frame = pop.to_frame()
    vuote = ind.SHAPE[0] * ind.SHAPE[1] * 2 * ind.SHAPE[3] * 2  # 80+ x {occupato, in_cerca}
    assert frame.height == int(np.prod(ind.SHAPE)) - vuote
    assert frame.columns == [
        "region_code",
        "region",
        "macro_area",
        "sex",
        "age_group",
        "age_band",
        "education",
        "employment",
        "count",
    ]
    assert ind.age_group_of(18) == "18_24"
    assert ind.age_group_of(49) == "45_49"
    assert ind.age_group_of(100) == "85_plus"
    assert ind.age_band_of_group("30_34") == "25_34"
    assert ind.age_band_of_group("85_plus") == "65_plus"
    with pytest.raises(ValueError, match="fuori"):
        ind.age_group_of(17)


def test_imprese(tables: IstatTables) -> None:
    frame = build_imprese(tables)
    assert frame["count"].sum() == tables.firms["count"].sum()
    assert (frame["count"] > 0).all()
    assert frame.columns == tables.firms.columns
