"""Codifica delle risposte e schemi JSON per domanda."""

import jsonschema
import pytest

from synthsurvey.interview import (
    AnswerStatus,
    code_value,
    describe_value,
    normalize_value,
    routing_value,
    status_for,
    text_value,
    value_schema,
)
from synthsurvey.questionnaire import DONT_KNOW_CODE, DONT_KNOW_LABEL, Mode, Questionnaire, adapt


def test_codifica_singola_multipla_scala_numerica_aperta(questionario: Questionnaire) -> None:
    q2 = questionario.question("q2")
    assert code_value(q2, "Servizio clienti") == "2" and text_value("Servizio clienti") == (
        "Servizio clienti"
    )
    assert code_value(q2, "Inesistente") is None
    assert code_value(q2, DONT_KNOW_CODE) == "NS" and text_value(DONT_KNOW_CODE) == (
        DONT_KNOW_LABEL
    )
    q4 = questionario.question("q4")
    assert code_value(q4, ["Passaparola", "Sito del fornitore"]) == "3|1"
    assert text_value(["a", "b"]) == "a | b"
    assert code_value(questionario.question("q1"), 7) == "7"
    assert code_value(questionario.question("q6"), 123.5) == "123.5"
    assert code_value(questionario.question("q7"), "testo") is None
    q5 = questionario.question("q5")
    assert code_value(q5, 4, "a") == "4" and text_value({"a": 4}) is None
    assert status_for(None) is AnswerStatus.NONRESPONSE
    assert (
        status_for("") is AnswerStatus.ANSWERED
        and status_for("", open_question=True) is AnswerStatus.NONRESPONSE
    )
    assert status_for([]) is AnswerStatus.NONRESPONSE
    assert status_for(DONT_KNOW_LABEL) is AnswerStatus.DONT_KNOW
    assert routing_value(DONT_KNOW_LABEL) == DONT_KNOW_CODE
    assert routing_value({"a": DONT_KNOW_LABEL, "b": 3}) == {"a": DONT_KNOW_CODE, "b": 3}
    assert describe_value({"a": 1, "b": None}) == "a=1, b=(nessuna risposta)"


def test_schemi_per_tipo(questionario: Questionnaire) -> None:
    mq = adapt(questionario, Mode.CAWI)
    s1 = value_schema(mq.question("q1"))
    assert s1 == {
        "anyOf": [
            {"type": "integer", "enum": list(range(1, 11))},
            {"type": "string", "enum": [DONT_KNOW_LABEL]},
        ]
    }
    s2 = value_schema(mq.question("q2"), ["Altro", "Prezzo", "Servizio clienti", DONT_KNOW_LABEL])
    assert s2["anyOf"][0] == {"type": "string", "enum": ["Altro", "Prezzo", "Servizio clienti"]}
    s4 = value_schema(mq.question("q4"))
    assert s4["anyOf"][0]["type"] == "array" if "anyOf" in s4 else s4["type"] == "array"
    s5 = value_schema(mq.question("q5"))
    assert set(s5["properties"]) == {"a", "b", "c"} and s5["additionalProperties"] is False
    assert value_schema(mq.question("q7")) == {"type": "string"}
    s6 = value_schema(mq.question("q6"))
    assert s6["anyOf"][0] == {"type": "number"}
    for s, esempio in ((s1, 3), (s1, DONT_KNOW_LABEL), (s5, {"a": 1, "b": 5, "c": 2})):
        jsonschema.validate(esempio, s)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(11, s1)


def test_normalizzazione(questionario: Questionnaire) -> None:
    mq = adapt(questionario, Mode.CAWI)
    q1, q2, q4 = mq.question("q1"), mq.question("q2"), mq.question("q4")
    q5, q6, q7 = mq.question("q5"), mq.question("q6"), mq.question("q7")
    assert normalize_value(q1, 7) == 7 and normalize_value(q1, "7") == 7
    assert normalize_value(q1, 11) is None and normalize_value(q1, 7.5) is None
    assert normalize_value(q1, DONT_KNOW_LABEL) == DONT_KNOW_CODE
    assert normalize_value(q2, "Prezzo") == "Prezzo" and normalize_value(q2, "boh") is None
    assert normalize_value(q2, "Prezzo", ["Altro"]) is None, "solo fra le opzioni presentate"
    assert normalize_value(q4, ["Passaparola", "Passaparola", "x"]) == ["Passaparola"]
    assert normalize_value(q4, "Passaparola") == ["Passaparola"]
    assert normalize_value(
        q4, ["Sito del fornitore", "Comparatori online", "Passaparola", "Punto vendita"]
    ) == [
        "Sito del fornitore",
        "Comparatori online",
        "Passaparola",
    ], "max_choices rispettato"
    assert normalize_value(q4, []) is None
    assert normalize_value(q5, {"a": 1, "b": "2", "c": DONT_KNOW_LABEL}) == {
        "a": 1,
        "b": 2,
        "c": DONT_KNOW_CODE,
    }
    assert normalize_value(q5, {"a": 9}) == {"a": None, "b": None, "c": None}
    assert normalize_value(q6, "120,5") == 120.5 and normalize_value(q6, 6000) is None
    assert normalize_value(q6, -1) is None and normalize_value(q6, True) is None
    assert normalize_value(q7, "  ") is None and normalize_value(q7, " ok ") == "ok"
    # "non so" su una domanda che non lo ammette non è codificabile.
    assert normalize_value(q7, DONT_KNOW_LABEL) is None
