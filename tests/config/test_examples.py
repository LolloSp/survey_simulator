"""Le configurazioni di esempio nel repository devono caricare senza errori."""

from pathlib import Path

import pytest

from synthsurvey.config import Design, estimate_interviews, load_config, segment_sizes
from tests.config.conftest import ESEMPI, ESEMPI_DIR


def test_ci_sono_cinque_esempi() -> None:
    assert [p.name for p in ESEMPI] == [
        "mercato_100.yaml",
        "mercato_1000.yaml",
        "mercato_100_ensemble.yaml",
        "mercato_500.yaml",
        "pilota_sessione.yaml",
    ]


@pytest.mark.parametrize("path", ESEMPI, ids=[p.stem for p in ESEMPI])
def test_esempio_valido(path: Path) -> None:
    loaded = load_config(path)
    cfg = loaded.config
    assert cfg.questionnaire.path.is_absolute()
    assert cfg.questionnaire.path.is_file()
    assert cfg.output.dir.is_absolute()
    assert sum(segment_sizes(cfg).values()) == cfg.sample.total
    # Gli avvisi ammessi negli esempi riguardano solo le celle piccole.
    assert all("quotas." in w.location for w in loaded.warnings), loaded.warnings


def test_esempio_100_caso_di_riferimento() -> None:
    cfg = load_config(ESEMPI[0]).config
    assert segment_sizes(cfg) == {"consumer": 70, "pmi": 30}
    stima = estimate_interviews(cfg)
    assert (stima.personas, stima.modes_per_persona, stima.replicates, stima.models) == (
        100,
        3,
        3,
        1,
    )
    assert stima.interviews == 900


def test_esempio_500_between_subject() -> None:
    cfg = load_config(ESEMPI_DIR / "mercato_500.yaml").config
    assert cfg.modes.design is Design.BETWEEN_SUBJECT
    assert estimate_interviews(cfg).modes_per_persona == 1
    assert estimate_interviews(cfg).interviews == 500 * 3


def test_esempio_1000_ensemble() -> None:
    cfg = load_config(ESEMPI_DIR / "mercato_1000.yaml").config
    assert len(cfg.engine.models) == 2
    assert cfg.engine.nonverbal.enabled is False
    assert estimate_interviews(cfg).interviews == 1000 * 3 * 3 * 2
