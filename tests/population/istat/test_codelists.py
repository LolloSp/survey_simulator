"""Le mappature ISTAT -> categorie del progetto sono complete e coerenti."""

import pytest

from survey_simulator.population import categories as cat
from survey_simulator.population.istat import codelists as cl


def test_regioni_complete_e_univoche() -> None:
    slugs = [v[0] for v in cl.REGIONS.values()]
    assert sorted(slugs) == sorted(cat.REGIONS)
    assert len(set(slugs)) == 20
    assert {v[1] for v in cl.REGIONS.values()} == set(cat.MACRO_AREAS)


@pytest.mark.parametrize(
    ("mapping", "categorie"),
    [
        (cl.EDUCATION_CENSUS, cat.EDUCATION),
        (cl.EDUCATION_LFS, cat.EDUCATION),
        (cl.EMPLOYMENT_CENSUS, cat.EMPLOYMENT),
        (cl.SIZE_CLASS_ASIA, (*cat.SIZE_CLASSES_PMI, cat.SIZE_CLASS_LARGE)),
        (cl.SECTOR_BY_DIVISION, cat.SECTORS),
        (cl.SEX_NUMERIC, cat.SEX),
        (cl.SEX_LETTER, cat.SEX),
    ],
)
def test_mappature_coprono_tutte_le_categorie(
    mapping: dict[str, str], categorie: tuple[str, ...]
) -> None:
    assert set(mapping.values()) == set(categorie)


@pytest.mark.parametrize(
    ("divisione", "settore"),
    [
        ("01", None),  # agricoltura esclusa
        ("05", "industria"),
        ("35", "industria"),
        ("39", "industria"),
        ("41", "costruzioni"),
        ("43", "costruzioni"),
        ("45", "commercio"),
        ("47", "commercio"),
        ("49", "trasporti_turismo"),
        ("56", "trasporti_turismo"),
        ("58", "servizi_imprese"),
        ("68", "servizi_imprese"),
        ("82", "servizi_imprese"),
        ("84", None),  # pubblica amministrazione esclusa
        ("85", "altri_servizi"),
        ("96", "altri_servizi"),
        ("97", None),
        ("99", None),
        ("0010", None),  # totale ISTAT
        ("C", None),  # sezione, non divisione
    ],
)
def test_settore_per_divisione(divisione: str, settore: str | None) -> None:
    assert cl.sector_for_division(divisione) == settore
    assert cl.SECTOR_BY_DIVISION.get(divisione) == settore


@pytest.mark.parametrize(
    ("codice", "eta"),
    [("Y0", 0), ("Y18", 18), ("Y99", 99), ("Y_GE100", 100), ("TOTAL", None), ("Y15-24", None)],
)
def test_eta_da_codice(codice: str, eta: int | None) -> None:
    assert cl.age_from_code(codice) == eta


@pytest.mark.parametrize(
    ("eta", "fascia"),
    [(18, "18_24"), (24, "18_24"), (25, "25_34"), (64, "55_64"), (65, "65_plus"), (100, "65_plus")],
)
def test_fascia_di_eta(eta: int, fascia: str) -> None:
    assert cl.age_band(eta) == fascia


def test_fascia_di_eta_minorenni_rifiutati() -> None:
    with pytest.raises(ValueError, match="fuori dal campo"):
        cl.age_band(17)
