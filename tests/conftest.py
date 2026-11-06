"""Opzioni globali dei test.

I test marcati `network` chiamano davvero l'API ISTAT e sono esclusi per
default (anche in CI): si abilitano con `pytest --network`.
"""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--network",
        action="store_true",
        default=False,
        help="esegue anche i test che usano la rete (API ISTAT)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "network: test che chiama l'API ISTAT reale")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--network"):
        return
    salta = pytest.mark.skip(reason="richiede la rete: usa `pytest --network`")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(salta)
