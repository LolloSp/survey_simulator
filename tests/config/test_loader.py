"""Caricamento del file: errori di I/O, YAML, schema; risoluzione dei percorsi; avvisi."""

from pathlib import Path
from typing import Any

import pytest

from synthsurvey.config import ConfigError, load_config, parse_config
from tests.config.conftest import Carica, Scrivi


def errori(exc: ConfigError) -> list[str]:
    return [f"{i.location}: {i.message}" for i in exc.issues]


def test_file_mancante(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as info:
        load_config(tmp_path / "inesistente.yaml")
    assert "file non trovato" in str(info.value)


def test_yaml_malformato(tmp_path: Path) -> None:
    path = tmp_path / "rotto.yaml"
    path.write_text("project: [a, b\nsample: {", encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert "YAML malformato" in str(info.value)


def test_yaml_non_mappa(tmp_path: Path) -> None:
    path = tmp_path / "lista.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert "mappa di sezioni" in str(info.value)


def test_config_valida_carica(base: dict[str, Any], carica: Carica) -> None:
    loaded = carica(base)
    assert loaded.config.project.name == "test-config"
    assert loaded.config.sample.total == 100
    assert loaded.warnings == []


def test_percorsi_relativi_alla_cartella_della_config(
    base: dict[str, Any], scrivi_config: Scrivi, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = scrivi_config(base)
    # Cambiare la cwd non deve cambiare la risoluzione dei percorsi.
    altra = tmp_path / "altrove"
    altra.mkdir()
    monkeypatch.chdir(altra)
    cfg = load_config(path).config
    assert cfg.questionnaire.path == (tmp_path / "questionario.yaml").resolve()
    assert cfg.output.dir == (tmp_path / "runs").resolve()


def test_percorso_assoluto_rispettato(base: dict[str, Any], carica: Carica, tmp_path: Path) -> None:
    q = tmp_path / "sub" / "q.yaml"
    q.parent.mkdir()
    q.write_text("id: q\n", encoding="utf-8")
    base["questionnaire"]["path"] = str(q)
    assert carica(base).config.questionnaire.path == q


def test_questionario_mancante_e_errore(base: dict[str, Any], carica: Carica) -> None:
    base["questionnaire"]["path"] = "non_esiste.yaml"
    with pytest.raises(ConfigError) as info:
        carica(base)
    assert any(e.startswith("questionnaire.path: file non trovato") for e in errori(info.value))


def test_chiave_sconosciuta_rifiutata(base: dict[str, Any], carica: Carica) -> None:
    base["sample"]["totale"] = 100
    with pytest.raises(ConfigError) as info:
        carica(base)
    assert any(e.startswith("sample.totale") for e in errori(info.value))


def test_sezione_mancante(base: dict[str, Any], carica: Carica) -> None:
    del base["engine"]
    with pytest.raises(ConfigError) as info:
        carica(base)
    assert any(e.startswith("engine:") for e in errori(info.value))


def test_piu_errori_riportati_insieme(base: dict[str, Any], carica: Carica) -> None:
    base["project"]["seed"] = -1
    base["engine"]["replicates"] = 0
    base["engine"]["temperature"] = 5
    with pytest.raises(ConfigError) as info:
        carica(base)
    locs = [i.location for i in info.value.issues]
    assert {"project.seed", "engine.replicates", "engine.temperature"} <= set(locs)


def test_messaggio_errore_leggibile(base: dict[str, Any], carica: Carica) -> None:
    base["sample"]["segments"]["consumer"]["share"] = 0.5
    with pytest.raises(ConfigError) as info:
        carica(base)
    testo = str(info.value)
    assert testo.startswith("Configurazione non valida:")
    assert "  - sample.segments: le share dei segmenti sommano a 0.8000, non a 1" in testo


def test_parse_config_in_memoria(base: dict[str, Any]) -> None:
    cfg = parse_config(base)
    assert cfg.engine.replicates == 3
    assert cfg.run.pilot_size == 12


def test_default_applicati(base: dict[str, Any], carica: Carica) -> None:
    del base["output"]
    base["engine"].pop("temperature", None)
    del base["engine"]["replicates"]
    del base["run"]["pilot_size"]
    cfg = carica(base).config
    assert [f.value for f in cfg.output.formats] == ["parquet", "csv", "sav"]
    assert cfg.engine.temperature is None
    assert cfg.engine.effort == "low" and cfg.engine.concurrency == 4
    assert cfg.engine.replicates == 3
    assert cfg.engine.randomize_option_order is True
    assert cfg.engine.nonverbal.enabled is True
    assert cfg.run.pilot_size == 12
