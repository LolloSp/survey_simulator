"""Regole incrociate: allocazione dei segmenti, coerenza con le sorgenti, avvisi."""

from typing import Any

import pytest

from synthsurvey.config import (
    ConfigError,
    Level,
    estimate_interviews,
    parse_config,
    segment_sizes,
    validate_config,
)
from synthsurvey.config.sources import SOURCES, UnknownSourceError, get_source


def errori(base: dict[str, Any]) -> list[str]:
    with pytest.raises(ConfigError) as info:
        validate_config(parse_config(base))
    return [f"{i.location}: {i.message}" for i in info.value.issues]


def avvisi(base: dict[str, Any]) -> list[str]:
    return [f"{w.location}: {w.message}" for w in validate_config(parse_config(base))]


def ha_errore(base: dict[str, Any], location: str, frammento: str = "") -> bool:
    return any(e.startswith(location) and frammento in e for e in errori(base))


# --- allocazione dei segmenti ------------------------------------------------


def test_share_non_sommano_a_uno(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["pmi"]["share"] = 0.4
    assert ha_errore(base, "sample.segments:", "sommano a 1.1000, non a 1")


def test_size_non_sommano_al_totale(base: dict[str, Any]) -> None:
    for seg, n in (("consumer", 70), ("pmi", 20)):
        del base["sample"]["segments"][seg]["share"]
        base["sample"]["segments"][seg]["size"] = n
    assert ha_errore(base, "sample.segments:", "sommano a 90, non a sample.total=100")


def test_size_valide(base: dict[str, Any]) -> None:
    for seg, n in (("consumer", 70), ("pmi", 30)):
        del base["sample"]["segments"][seg]["share"]
        base["sample"]["segments"][seg]["size"] = n
    assert avvisi(base) == []
    assert segment_sizes(parse_config(base)) == {"consumer": 70, "pmi": 30}


def test_share_e_size_mescolati(base: dict[str, Any]) -> None:
    del base["sample"]["segments"]["pmi"]["share"]
    base["sample"]["segments"]["pmi"]["size"] = 30
    assert ha_errore(base, "sample.segments:", "non mescolare share")


def test_segmento_con_entrambi(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["pmi"]["size"] = 30
    assert ha_errore(base, "sample.segments.pmi:", "non entrambi")


def test_segmento_senza_nessuno(base: dict[str, Any]) -> None:
    del base["sample"]["segments"]["pmi"]["share"]
    assert ha_errore(base, "sample.segments.pmi:", "indicare share oppure size")


def test_proportional_ignora_share_con_avviso(base: dict[str, Any]) -> None:
    base["sample"]["allocation"] = "proportional"
    assert any("share e size sono ignorati" in a for a in avvisi(base))
    assert sum(segment_sizes(parse_config(base)).values()) == 100


def test_proportional_senza_share(base: dict[str, Any]) -> None:
    base["sample"]["allocation"] = "proportional"
    for seg in base["sample"]["segments"].values():
        del seg["share"]
    assert avvisi(base) == []


def test_segment_sizes_compensa_arrotondamenti(base: dict[str, Any]) -> None:
    base["sample"]["total"] = 101
    base["sample"]["segments"]["consumer"]["share"] = 0.5
    base["sample"]["segments"]["pmi"]["share"] = 0.5
    sizes = segment_sizes(parse_config(base))
    assert sum(sizes.values()) == 101


# --- coerenza con le sorgenti -------------------------------------------------


def test_sorgente_sconosciuta(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["source"] = "istat_marziani"
    assert ha_errore(base, "sample.segments.consumer.source", "disponibili: istat_imprese")


def test_quota_non_disponibile_nella_sorgente(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["quotas"] = ["sex", "size_class"]
    assert ha_errore(base, "sample.segments.consumer.quotas", "size_class")


def test_oversample_variabile_sconosciuta(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["pmi"]["oversample"] = {"colore": {"rosso": 1.0}}
    assert ha_errore(base, "sample.segments.pmi.oversample.colore")


def test_oversample_categoria_sconosciuta(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["pmi"]["oversample"] = {"size_class": {"micro": 0.5, "grande": 0.5}}
    assert ha_errore(base, "sample.segments.pmi.oversample.size_class", "grande")


def test_filtro_sconosciuto(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["filters"] = {"altezza": [150, 200]}
    assert ha_errore(base, "sample.segments.consumer.filters.altezza", "ammessi: age")


def test_filtro_intervallo_invertito(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["filters"] = {"age": [60, 30]}
    assert ha_errore(base, "sample.segments.consumer.filters.age", "invertito")


def test_filtro_intervallo_fuori_limiti(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["filters"] = {"age": [10, 120]}
    assert ha_errore(base, "sample.segments.consumer.filters.age", "fuori dai limiti")


def test_filtro_intervallo_attende_lista(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["filters"] = {"age": "all"}
    assert ha_errore(base, "sample.segments.consumer.filters.age", "intervallo")


def test_filtro_categorico_attende_lista_o_all(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["filters"] = {"region": [1, 2]}
    assert ha_errore(base, "sample.segments.consumer.filters.region", "lista di categorie")


def test_filtro_categoria_sconosciuta(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["filters"] = {"region": ["lombardia", "padania"]}
    assert ha_errore(base, "sample.segments.consumer.filters.region", "padania")


def test_filtro_categorie_valide(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["filters"] = {"region": ["lombardia", "lazio"]}
    assert avvisi(base) == []


def test_ruolo_su_individui(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["respondent_role"] = ["titolare"]
    assert ha_errore(base, "sample.segments.consumer.respondent_role", "solo per segmenti")


def test_ruolo_sconosciuto(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["pmi"]["respondent_role"] = ["titolare", "stagista"]
    assert ha_errore(base, "sample.segments.pmi.respondent_role", "stagista")


def test_piu_errori_di_sorgente_insieme(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["consumer"]["quotas"] = ["sex", "sector"]
    base["sample"]["segments"]["pmi"]["respondent_role"] = ["stagista"]
    errs = errori(base)
    assert any(e.startswith("sample.segments.consumer.quotas") for e in errs)
    assert any(e.startswith("sample.segments.pmi.respondent_role") for e in errs)


# --- combinazioni impossibili ------------------------------------------------


def test_oversample_classe_esclusa_dal_filtro(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["pmi"]["filters"]["employees"] = [10, 249]
    assert ha_errore(base, "sample.segments.pmi.oversample.size_class", "micro")


def test_oversample_classe_esclusa_ma_a_zero(base: dict[str, Any]) -> None:
    base["sample"]["segments"]["pmi"]["filters"]["employees"] = [10, 249]
    base["sample"]["segments"]["pmi"]["oversample"] = {"size_class": {"piccola": 0.6, "media": 0.4}}
    assert not any("impossibile" in a for a in avvisi(base))


# --- avvisi ----------------------------------------------------------------------


def test_celle_piccole(base: dict[str, Any]) -> None:
    base["sample"]["total"] = 20
    avv = avvisi(base)
    # consumer: 14 persone / 6 fasce di età = 2.3 casi; pmi: 6 / 6 settori = 1.
    assert any(a.startswith("sample.segments.consumer.quotas.age_band") for a in avv)
    assert any(a.startswith("sample.segments.pmi.quotas.sector") for a in avv)
    assert any("accorpare le categorie di sector fino a un massimo di 2" in a for a in avv)
    # sex (2 categorie, 7 casi) non genera avviso.
    assert not any("quotas.sex" in a for a in avv)


def test_celle_piccole_sono_avvisi_non_errori(base: dict[str, Any]) -> None:
    base["sample"]["total"] = 20
    for w in validate_config(parse_config(base)):
        assert w.level is Level.WARNING


def test_allocation_ignorata_in_within_subject(base: dict[str, Any]) -> None:
    base["modes"]["allocation"] = {"cawi": 0.34, "cati": 0.33, "capi": 0.33}
    assert any(a.startswith("modes.allocation: ignorata") for a in avvisi(base))


def test_pilot_size_maggiore_del_totale(base: dict[str, Any]) -> None:
    base["run"]["pilot_size"] = 500
    assert ha_errore(base, "run.pilot_size", "supera sample.total=100")


# --- stima del volume --------------------------------------------------------


def test_stima_pilota(base: dict[str, Any]) -> None:
    base["run"]["pilot"] = True
    stima = estimate_interviews(parse_config(base))
    assert stima.personas == 12
    assert stima.interviews == 12 * 3 * 3


# --- registro sorgenti ---------------------------------------------------------


def test_registro_sorgenti() -> None:
    assert set(SOURCES) == {"istat_individui", "istat_imprese"}
    assert get_source("istat_imprese").unit == "imprese"
    with pytest.raises(UnknownSourceError, match="sconosciuta"):
        get_source("nope")
