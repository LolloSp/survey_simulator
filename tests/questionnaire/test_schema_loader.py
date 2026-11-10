"""Schema del questionario: esempio valido, errori per tipo, caricamento, coerenza con la config."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from survey_simulator.config import load_config
from survey_simulator.questionnaire import (
    Questionnaire,
    QuestionnaireError,
    QuestionType,
    check_against_config,
    load_questionnaire,
    parse_questionnaire,
)
from tests.config.conftest import ESEMPI_DIR
from tests.questionnaire.conftest import ESEMPIO, domanda


def errori(raw: dict[str, Any]) -> list[str]:
    with pytest.raises(QuestionnaireError) as info:
        parse_questionnaire(raw)
    return info.value.issues


def test_esempio_valido(esempio: Questionnaire) -> None:
    assert esempio.id == "mercato_v1"
    assert len(esempio.sections) == 3
    assert [q.id for q in esempio.questions] == [f"q{i}" for i in range(1, 11)]
    assert esempio.question("q5").type is QuestionType.GRID
    assert esempio.segments() == {"consumer", "pmi"}
    assert esempio.question("q2").randomizable_options == [
        "Prezzo",
        "Servizio clienti",
        "Trasparenza della bolletta",
    ]


def test_hash_e_avvisi_con_config() -> None:
    cfg = load_config(ESEMPI_DIR / "mercato_100.yaml").config
    loaded = load_questionnaire(ESEMPIO, cfg)
    assert len(loaded.sha256) == 64
    assert loaded.warnings == []


@pytest.mark.parametrize(
    ("qid", "modifica", "frammento"),
    [
        ("q1", {"scale": {"min": 5, "max": 5}}, "non maggiore"),
        ("q1", {"scale": {"min": 1, "max": 10, "labels": {11: "x"}}}, "fuori dalla scala"),
        ("q1", {"options": ["a", "b"]}, "options e items non ammessi"),
        ("q2", {"options": ["a"]}, "almeno due"),
        ("q2", {"options": ["a", "a"]}, "duplicati"),
        ("q2", {"options": ["a", " "]}, "vuote"),
        ("q2", {"options": None}, "servono le options"),
        ("q2", {"fixed_last": ["Boh"]}, "fixed_last"),
        ("q2", {"max_choices": 2}, "solo per multi"),
        ("q4", {"max_choices": 9}, "maggiore del numero"),
        ("q5", {"items": []}, "items"),
        ("q5", {"options": ["a", "b"]}, "esattamente uno"),
        ("q5", {"items": [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}]}, "duplicati"),
        ("q6", {"min": 10, "max": 5}, "non maggiore"),
        ("q7", {"min": 0}, "solo per numeric"),
        ("q7", {"randomize": True}, "randomize"),
        ("q8", {"applies_to": []}, "applies_to vuoto"),
        ("q1", {"id": "Q1"}, "pattern"),
        ("q1", {"colore": "rosso"}, "colore"),
    ],
)
def test_domanda_non_valida(
    raw: dict[str, Any], qid: str, modifica: dict[str, Any], frammento: str
) -> None:
    d = domanda(raw, qid)
    for k, v in modifica.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    assert any(frammento in e for e in errori(raw)), errori(raw)


def test_id_duplicati(raw: dict[str, Any]) -> None:
    domanda(raw, "q3")["id"] = "q2"
    assert any("duplicati" in e for e in errori(raw))


def test_sezione_vuota(raw: dict[str, Any]) -> None:
    raw["sections"][0]["questions"] = []
    assert errori(raw)


def test_file_mancante_e_yaml_rotto(tmp_path: Path) -> None:
    with pytest.raises(QuestionnaireError, match="non trovato"):
        load_questionnaire(tmp_path / "no.yaml")
    rotto = tmp_path / "rotto.yaml"
    rotto.write_text("sections: [\n", encoding="utf-8")
    with pytest.raises(QuestionnaireError, match="malformato"):
        load_questionnaire(rotto)
    lista = tmp_path / "lista.yaml"
    lista.write_text("- a\n", encoding="utf-8")
    with pytest.raises(QuestionnaireError, match="mappa"):
        load_questionnaire(lista)


def test_segmenti_contro_config(
    esempio: Questionnaire, raw: dict[str, Any], tmp_path: Path
) -> None:
    cfg = load_config(ESEMPI_DIR / "mercato_100.yaml").config
    assert check_against_config(esempio, cfg) == []
    domanda(raw, "q8")["applies_to"] = ["pmi", "enti"]
    path = tmp_path / "q.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(QuestionnaireError, match="enti"):
        load_questionnaire(path, cfg)


def test_avviso_segmento_senza_domande(raw: dict[str, Any], tmp_path: Path) -> None:
    cfg = load_config(ESEMPI_DIR / "mercato_100.yaml").config
    for s in raw["sections"]:
        for q in s["questions"]:
            q["applies_to"] = ["consumer"]
    path = tmp_path / "q.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    loaded = load_questionnaire(path, cfg)
    assert loaded.warnings == ["nessuna domanda si applica al segmento pmi"]


def test_rilancio_e_nota_di_codifica(raw: dict[str, Any]) -> None:
    q7 = domanda(raw, "q7")
    q7["probe"] = "E l'energia, dove sta in questa lista?"
    q7["coding_note"] = "Energia citata spontaneamente: sì/no"
    q = parse_questionnaire(raw)
    assert q.question("q7").probe == "E l'energia, dove sta in questa lista?"
    assert q.question("q7").coding_note == "Energia citata spontaneamente: sì/no"
    assert q.question("q1").probe is None and q.question("q1").coding_note is None
    q7["probe"] = "  "
    assert any("probe vuoto" in e for e in errori(raw))
    q7["probe"] = "Rilancio"
    domanda(raw, "q5")["probe"] = "Per ogni riga?"
    assert any("probe non ammesso per grid" in e for e in errori(raw))
