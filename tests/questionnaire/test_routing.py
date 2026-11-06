"""Linguaggio delle show_if: parsing, valutazione, validazione contro il questionario, percorso."""

from typing import Any

import pytest

from synthsurvey.questionnaire import (
    DONT_KNOW_CODE,
    Questionnaire,
    RoutingError,
    evaluate,
    next_question,
    parse,
    parse_questionnaire,
    route,
    validate_show_if,
)
from synthsurvey.questionnaire.routing import references, tokenize
from tests.questionnaire.conftest import domanda


def ev(expr: str, answers: dict[str, Any]) -> bool:
    return evaluate(parse(expr), answers)


@pytest.mark.parametrize(
    ("expr", "answers", "atteso"),
    [
        ("q1 <= 5", {"q1": 3}, True),
        ("q1 <= 5", {"q1": 7}, False),
        ("q1 <= 5", {}, False),
        ("q1 <= 5", {"q1": DONT_KNOW_CODE}, False),
        ('q2 == "Prezzo"', {"q2": "Prezzo"}, True),
        ('q2 != "Prezzo"', {"q2": "Altro"}, True),
        ('q2 != "Prezzo"', {}, False),
        ('q3 in ["Sì, ho cambiato", "No"]', {"q3": "No"}, True),
        ('q3 not in ["No"]', {"q3": "No"}, False),
        ('q4 contains "Passaparola"', {"q4": ["Pubblicità", "Passaparola"]}, True),
        ('q4 contains "Passaparola"', {"q4": ["Pubblicità"]}, False),
        ("q5.a >= 4", {"q5": {"a": 5, "b": 1}}, True),
        ("q5.b >= 4", {"q5": {"a": 5, "b": 1}}, False),
        ("q5.c >= 4", {"q5": {"a": 5}}, False),
        ("answered(q1)", {"q1": 0}, True),
        ("answered(q1)", {"q1": DONT_KNOW_CODE}, False),
        ("answered(q4)", {"q4": []}, False),
        ("not answered(q1)", {}, True),
        ("(q1 > 7 or q6 < 100) and answered(q3)", {"q1": 9, "q3": "No"}, True),
        ("(q1 > 7 or q6 < 100) and answered(q3)", {"q1": 9}, False),
        ("q1 > 7 or q6 < 100", {"q6": 50}, True),
        ("true", {}, True),
        ("not false", {}, True),
        ("q6 >= 1.5", {"q6": 2.0}, True),
        ('q2 == "con \\"virgolette\\""', {"q2": 'con "virgolette"'}, True),
    ],
)
def test_valutazione(expr: str, answers: dict[str, Any], atteso: bool) -> None:
    assert ev(expr, answers) is atteso


@pytest.mark.parametrize(
    "expr",
    [
        "",
        "q1 <",
        "q1 <= ",
        "q1 = 5",
        "(q1 > 2",
        "q1 > 2)",
        "q1 in 5",
        "q1 in [1,",
        "and q1 > 2",
        "q1 § 2",
        "answered q1",
        "q1 > 2 extra",
    ],
)
def test_espressioni_malformate(expr: str) -> None:
    with pytest.raises(RoutingError):
        parse(expr)


def test_confronto_di_ordine_fra_testi() -> None:
    with pytest.raises(RoutingError, match="ordine"):
        ev('q2 < "b"', {"q2": "a"})


def test_tokenizer_e_riferimenti() -> None:
    toks = tokenize('q5.a >= 4 and q2 == "x"')
    assert [t.kind for t in toks] == ["ident", "op", "number", "kw", "ident", "op", "string"]
    assert references(parse("(q1 > 2 or q5.a == 1) and answered(q3)")) == {"q1", "q5.a", "q3"}


def test_validazione_show_if_esempio(esempio: Questionnaire) -> None:
    assert validate_show_if(esempio) == []


@pytest.mark.parametrize(
    ("qid", "show_if", "frammento"),
    [
        ("q2", 'q9 == "x"', "non è una domanda precedente"),
        ("q2", "q2 <= 5", "la domanda stessa"),
        ("q2", 'q1 == "alto"', "risposte numeriche"),
        ("q2", "q1 <= 11", "fuori dalla scala"),
        ("q3", 'q2 == "Boh"', "non è un'opzione"),
        ("q3", 'q2 < "Prezzo"', "ordine"),
        ("q3", 'q2 contains "Prezzo"', "solo su domande multi"),
        ("q6", "q5 >= 4", "indicare l'item"),
        ("q6", "q5.z >= 4", "assente nella griglia"),
        ("q6", "q4.a == 1", "non è una griglia"),
        ("q6", "q1 <=", "atteso un valore"),
    ],
)
def test_show_if_incoerenti(raw: dict[str, Any], qid: str, show_if: str, frammento: str) -> None:
    domanda(raw, qid)["show_if"] = show_if
    with pytest.raises(Exception, match=frammento):
        parse_questionnaire(raw)


def test_percorso_consumer(esempio: Questionnaire) -> None:
    answers: dict[str, Any] = {}
    visto: list[str] = []
    risposte = {
        "q1": 3,
        "q2": "Prezzo",
        "q3": "No",
        "q5": {"a": 2, "b": 4, "c": 3},
        "q6": 120,
        "q7": "Nessuno",
        "q10": 2000,
    }
    while (q := next_question(esempio, "consumer", answers)) is not None:
        visto.append(q.id)
        answers[q.id] = risposte[q.id]
    # q4 saltata (q3 = No), q8 e q9 solo pmi.
    assert visto == ["q1", "q2", "q3", "q5", "q6", "q7", "q10"]
    assert [q.id for q in route(esempio, "consumer", answers)] == visto


def test_percorso_pmi(esempio: Questionnaire) -> None:
    answers: dict[str, Any] = {
        "q1": 9,
        "q3": "Sì, ho cambiato",
        "q4": ["Comparatori online"],
        "q5": {},
        "q6": 900,
        "q8": "Un consulente esterno",
    }
    ids = [q.id for q in route(esempio, "pmi", answers)]
    assert ids == ["q1", "q3", "q4", "q5", "q6", "q8"], (
        ids
    )  # q2 (q1 > 5), q7 (q1 > 7), q9 (consulente) e q10 (consumer) saltate


def test_next_question_salta_dont_know(esempio: Questionnaire) -> None:
    assert next_question(esempio, "consumer", {"q1": DONT_KNOW_CODE}).id == "q3"
