"""Vincoli dello schema Pydantic: campo per campo e dentro una singola sezione."""

from typing import Any

import pytest

from synthsurvey.config import ConfigError, parse_config


def errori(base: dict[str, Any]) -> list[str]:
    with pytest.raises(ConfigError) as info:
        parse_config(base)
    return [f"{i.location}: {i.message}" for i in info.value.issues]


def ha_errore(base: dict[str, Any], location: str, frammento: str = "") -> bool:
    return any(e.startswith(location) and frammento in e for e in errori(base))


@pytest.mark.parametrize(
    ("sezione", "campo", "valore", "location"),
    [
        ("project", "name", "", "project.name"),
        ("project", "name", "Nome Con Spazi", "project.name"),
        ("project", "seed", -5, "project.seed"),
        ("project", "seed", "abc", "project.seed"),
        ("sample", "total", 0, "sample.total"),
        ("sample", "allocation", "casuale", "sample.allocation"),
        ("sample", "segments", {}, "sample.segments"),
        ("engine", "models", [], "engine.models"),
        ("engine", "temperature", -0.1, "engine.temperature"),
        ("engine", "temperature", 2.1, "engine.temperature"),
        ("engine", "replicates", 0, "engine.replicates"),
        ("engine", "replicates", 1.5, "engine.replicates"),
        ("run", "budget_max_eur", 0, "run.budget_max_eur"),
        ("run", "pilot_size", 0, "run.pilot_size"),
        ("run", "frozen", "forse", "run.frozen"),
        ("output", "formats", [], "output.formats"),
        ("output", "formats", ["xlsx"], "output.formats"),
        ("output", "formats", ["csv", "csv"], "output.formats"),
        ("modes", "enabled", [], "modes.enabled"),
        ("modes", "enabled", ["cawi", "fax"], "modes.enabled"),
        ("modes", "enabled", ["cawi", "cawi"], "modes.enabled"),
        ("modes", "design", "misto", "modes.design"),
    ],
)
def test_valore_non_valido(
    base: dict[str, Any], sezione: str, campo: str, valore: Any, location: str
) -> None:
    base[sezione][campo] = valore
    assert ha_errore(base, location), errori(base)


def test_segmento_quote_duplicate(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["quotas"] = ["sex", "age_band", "sex"]
    assert ha_errore(base, "sample.segments.consumer.quotas", "duplicati: sex")


def test_segmento_quote_vuote(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["quotas"] = []
    assert ha_errore(base, "sample.segments.consumer")


def test_segmento_share_fuori_intervallo(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["share"] = 1.5
    assert ha_errore(base, "sample.segments.consumer.share")
    base["sample"]["segments"]["consumer"]["share"] = 0
    assert ha_errore(base, "sample.segments.consumer.share")


def test_segmento_oversample_non_somma_a_uno(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["pmi"]["oversample"] = {"size_class": {"micro": 0.5, "media": 0.3}}
    assert ha_errore(base, "sample.segments.pmi.oversample", "sommano a 0.8000")


def test_segmento_filtro_tipo_errato(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["filters"] = {"age": "giovani"}
    assert ha_errore(base, "sample.segments.consumer.filters.age")


def test_segmento_chiave_sconosciuta(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["quote"] = ["sex"]
    assert ha_errore(base, "sample.segments.consumer.quote")


def test_modello_duplicato(base: dict[str, Any]) -> None:
    m = {"provider": "anthropic", "model": "x"}
    base["engine"]["models"] = [m, dict(m)]
    assert ha_errore(base, "engine.models", "duplicati")


def test_modello_campi_vuoti(base: dict[str, Any]) -> None:
    base["engine"]["models"] = [{"provider": "", "model": "x"}]
    assert ha_errore(base, "engine.models.0.provider")


def test_between_subject_senza_allocation(base: dict[str, Any]) -> None:
    base["modes"]["design"] = "between_subject"
    assert ha_errore(base, "modes", "allocation è obbligatoria")


def test_between_subject_allocation_incompleta(base: dict[str, Any]) -> None:
    base["modes"]["design"] = "between_subject"
    base["modes"]["allocation"] = {"cawi": 0.5, "cati": 0.5}
    assert ha_errore(base, "modes", "mancano capi")


def test_between_subject_allocation_modalita_non_abilitata(base: dict[str, Any]) -> None:
    base["modes"]["design"] = "between_subject"
    base["modes"]["enabled"] = ["cawi", "cati"]
    base["modes"]["allocation"] = {"cawi": 0.5, "cati": 0.3, "capi": 0.2}
    assert ha_errore(base, "modes", "non abilitate capi")


def test_between_subject_allocation_non_somma_a_uno(base: dict[str, Any]) -> None:
    base["modes"]["design"] = "between_subject"
    base["modes"]["allocation"] = {"cawi": 0.5, "cati": 0.3, "capi": 0.3}
    assert ha_errore(base, "modes", "somma a 1.1000")


def test_between_subject_valido(base: dict[str, Any]) -> None:
    base["modes"]["design"] = "between_subject"
    base["modes"]["allocation"] = {"cawi": 0.34, "cati": 0.33, "capi": 0.33}
    cfg = parse_config(base)
    assert cfg.modes.allocation is not None
    assert len(cfg.modes.allocation) == 3


def test_config_immutabile(base: dict[str, Any]) -> None:
    cfg = parse_config(base)
    with pytest.raises(Exception, match="frozen"):
        cfg.sample.total = 200  # type: ignore[misc]
