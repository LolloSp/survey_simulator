"""Interviste CATI e CAPI con il client finto: lettura, segnali, chiarimenti, approfondimenti."""

from typing import Any

import jsonschema

from synthsurvey.config import SynthSurveyConfig, parse_config
from synthsurvey.interview import (
    SIGNALS,
    AnswerStatus,
    InterviewSpec,
    run_dialogue,
    run_interview,
)
from synthsurvey.interview.dialogue import INTERVIEWER_SCHEMA, spoken_question
from synthsurvey.llm import FakeLLMClient, LLMPool, LLMRequest, fill_schema
from synthsurvey.personas.schema import Persona
from synthsurvey.questionnaire import (
    DONT_KNOW_LABEL,
    Mode,
    Questionnaire,
    adapt,
    parse_questionnaire,
)
from synthsurvey.questionnaire.modes import option_order
from tests.config.conftest import config_base

INTERVIEWER_MARK = "intervistatore professionista"


def spec(persona: Persona, mode: Mode = Mode.CATI, replicate: int = 1) -> InterviewSpec:
    return InterviewSpec(
        run_id="test",
        persona=persona,
        persona_index=0,
        mode=mode,
        replicate=replicate,
        model="fake-1",
        seed=42,
    )


def is_interviewer(r: LLMRequest) -> bool:
    return INTERVIEWER_MARK in r.system


def respondent_reply(r: LLMRequest, **override: Any) -> dict[str, Any]:
    assert r.schema is not None
    out = fill_schema(r.schema)
    out["clarification_requested"] = False
    out["clarification"] = None
    out["spoken"] = "Mah, direi la prima."
    if "nonverbal" in out:
        out["nonverbal"]["note"] = "penso davvero questo"
        out["nonverbal"]["body"] = {
            "espressione": "neutra",
            "sguardo": "dritto",
            "postura": "rilassata",
            "gesti": "nessuno",
        }
    out.update(override)
    return out


def interviewer_reply(action: str = "accept", **override: Any) -> dict[str, Any]:
    out = {
        "action": action,
        "utterance": "" if action == "accept" else "Certo, le rileggo la domanda.",
        "incongruence": False,
        "incongruence_note": None,
    }
    out.update(override)
    return out


def default_responder(r: LLMRequest) -> dict[str, Any]:
    return interviewer_reply() if is_interviewer(r) else respondent_reply(r)


def pool(responder: Any = default_responder, **kw: Any) -> LLMPool:
    return LLMPool(FakeLLMClient("fake-1", responder, **kw))


def by_question(result: Any) -> dict[tuple[str, str | None], Any]:
    return {(r.question_id, r.item_id): r for r in result.records}


def step(r: LLMRequest) -> str:
    return r.metadata.get("step", "")


async def test_cati_base(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    p = pool()
    mq = adapt(questionario, Mode.CATI)
    result = await run_dialogue(spec(persona), questionario, mq, p, config)
    rec = by_question(result)
    assert result.outcome.completed and result.outcome.refusals == 0
    assert (
        rec[("q1", None)].status is AnswerStatus.ANSWERED and rec[("q1", None)].answer_code == "1"
    )
    # Griglia spezzata al telefono: un record per item, risposte raccolte per il routing.
    assert {k for k in rec if k[0] == "q5"} == {("q5", "a"), ("q5", "b"), ("q5", "c")}
    assert rec[("q5", "b")].answer_code == "1" and result.answers["q5"] == {"a": 1, "b": 1, "c": 1}
    assert rec[("q8", None)].status is AnswerStatus.NOT_APPLICABLE
    mostrate = [r for r in result.records if r.status is AnswerStatus.ANSWERED]
    assert result.outcome.calls == len(mostrate), (
        "una chiamata per domanda letta, nessun intervistatore"
    )
    emesso = rec[("q1", None)].nonverbal_emitted
    osservato = rec[("q1", None)].nonverbal_observed
    assert (
        emesso is not None and set(SIGNALS) <= set(emesso) and emesso["body"]["sguardo"] == "dritto"
    )
    assert osservato is not None and "body" not in osservato, "al telefono il corpo non si vede"
    assert rec[("q1", None)].incongruence is None and rec[("q1", None)].probe is False
    parlanti = [t.speaker for t in result.transcript[:2]]
    assert parlanti == ["intervistatore", "rispondente"]
    assert result.transcript[1].signals == osservato
    assert sum(r.tokens_in for r in result.records) == result.outcome.tokens_in


async def test_capi_griglia_intera_e_cartellini(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    p = pool()
    client = p.client
    assert isinstance(client, FakeLLMClient)
    mq = adapt(questionario, Mode.CAPI)
    result = await run_dialogue(spec(persona, Mode.CAPI), questionario, mq, p, config)
    rec = by_question(result)
    assert rec[("q5", "c")].status is AnswerStatus.ANSWERED
    chiamate_q5 = [r for r in client.requests if step(r).startswith("q:q5")]
    assert len(chiamate_q5) == 1, "griglia intera: una sola chiamata"
    assert rec[("q5", "a")].tokens_in > 0 and rec[("q5", "b")].tokens_in == 0
    osservato = rec[("q1", None)].nonverbal_observed
    assert osservato is not None and osservato["body"]["espressione"] == "neutra"
    letture = [t.text for t in result.transcript if t.speaker == "intervistatore"]
    q1 = next(t for t in letture if t.startswith("Quanto è soddisfatto"))
    assert q1.lower().count("cartellino") == 1, "il cartellino della scala compare una volta sola"
    q4 = next(t for t in letture if t.startswith("Quali di questi canali"))
    assert "[Cartellino:" in q4 and q4.rstrip("]").endswith("Nessuno")
    assert "sei un intervistatore" not in client.requests[0].system.lower()
    assert "intervista di persona" in client.requests[0].system


async def test_chiarimento(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    def responder(r: LLMRequest) -> dict[str, Any]:
        if is_interviewer(r):
            assert "Ha chiesto un chiarimento" in r.messages[0].content
            return interviewer_reply("clarify", utterance="Certo: negli ultimi dodici mesi.")
        if step(r) == "q:q3:a":
            return respondent_reply(
                r,
                answer=None,
                clarification_requested=True,
                clarification="Intende quest'anno?",
                spoken="Scusi, intende quest'anno?",
            )
        if step(r) == "q:q3:b":
            assert r.messages[-1].content == "Certo: negli ultimi dodici mesi."
            return respondent_reply(r, answer="No", spoken="Allora no.")
        return respondent_reply(r)

    p = pool(responder)
    mq = adapt(questionario, Mode.CATI)
    result = await run_dialogue(spec(persona), questionario, mq, p, config)
    rec = by_question(result)
    q3 = rec[("q3", None)]
    assert q3.answer_text == "No" and q3.clarification_requested and not q3.probe
    assert rec[("q4", None)].status is AnswerStatus.NOT_APPLICABLE, "q3 = No nasconde q4"
    battute = [t.text for t in result.transcript if t.question_id == "q3"]
    assert battute[1] == "Scusi, intende quest'anno?"
    assert battute[2] == "Certo: negli ultimi dodici mesi." and battute[3] == "Allora no."
    answered = sum(1 for r in result.records if r.status is AnswerStatus.ANSWERED)
    assert result.outcome.calls == answered + 2


async def test_approfondimento_su_segnali_forti(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    def responder(r: LLMRequest) -> dict[str, Any]:
        if is_interviewer(r):
            assert "esitazione 3" in r.messages[0].content
            return interviewer_reply(
                "probe",
                utterance="Mi sembra di cogliere un'esitazione: conferma il 9?",
                incongruence=True,
                incongruence_note="voto alto detto con esitazione forte",
            )
        if step(r) == "q:q1:a":
            out = respondent_reply(r, answer=9, spoken="Nove... sì, nove.")
            out["nonverbal"]["esitazione"] = 3
            return out
        if step(r) == "q:q1:b":
            return respondent_reply(r, answer=4, spoken="Beh, forse un quattro.")
        return respondent_reply(r)

    p = pool(responder)
    result = await run_dialogue(
        spec(persona), questionario, adapt(questionario, Mode.CATI), p, config
    )
    rec = by_question(result)
    q1 = rec[("q1", None)]
    assert q1.answer_code == "4" and q1.probe and q1.incongruence is True
    assert rec[("q2", None)].status is AnswerStatus.ANSWERED, "4 <= 5 mostra q2"
    assert result.transcript[2].text.startswith("Mi sembra di cogliere")


async def test_intervistatore_accetta_con_incongruenza(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    def responder(r: LLMRequest) -> dict[str, Any]:
        if is_interviewer(r):
            return interviewer_reply("accept", incongruence=True, incongruence_note="voce piatta")
        out = respondent_reply(r)
        if step(r) == "q:q1:a":
            out["nonverbal"]["disinteresse"] = 2
        return out

    p = pool(responder)
    result = await run_dialogue(
        spec(persona), questionario, adapt(questionario, Mode.CATI), p, config
    )
    q1 = by_question(result)[("q1", None)]
    assert q1.answer_code == "1" and not q1.probe and q1.incongruence is True
    answered = sum(1 for r in result.records if r.status is AnswerStatus.ANSWERED)
    assert result.outcome.calls == answered + 1


async def test_risposta_non_codificabile(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    def responder(r: LLMRequest) -> dict[str, Any]:
        if is_interviewer(r):
            return interviewer_reply("probe", utterance="Anche una cifra approssimativa.")
        if step(r) == "q:q6:a":
            return respondent_reply(r, answer=None, spoken="Dipende dal mese.")
        if step(r) == "q:q6:b":
            return respondent_reply(r, answer=120, spoken="Diciamo centoventi.")
        if step(r) == "q:q7:a":
            return respondent_reply(r, answer="", spoken="Niente.")
        if step(r) == "q:q7:b":
            return respondent_reply(r, answer="", spoken="No, niente.")
        return respondent_reply(r)

    p = pool(responder)
    result = await run_dialogue(
        spec(persona), questionario, adapt(questionario, Mode.CATI), p, config
    )
    rec = by_question(result)
    assert rec[("q6", None)].answer_code == "120" and rec[("q6", None)].probe
    q7 = rec[("q7", None)]
    assert q7.status is AnswerStatus.NONRESPONSE and q7.item_nonresponse and q7.probe


async def test_non_so_spontaneo(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    def responder(r: LLMRequest) -> dict[str, Any]:
        assert not is_interviewer(r), "il non so spontaneo si accetta senza intervistatore"
        if step(r) == "q:q1:a":
            return respondent_reply(r, answer=DONT_KNOW_LABEL, spoken="Non saprei.")
        return respondent_reply(r)

    result = await run_dialogue(
        spec(persona), questionario, adapt(questionario, Mode.CATI), pool(responder), config
    )
    rec = by_question(result)
    assert rec[("q1", None)].status is AnswerStatus.DONT_KNOW
    assert rec[("q1", None)].answer_code == "NS"
    assert rec[("q2", None)].status is AnswerStatus.NOT_APPLICABLE
    assert rec[("q7", None)].status is AnswerStatus.NOT_APPLICABLE


async def test_segnali_disattivati(questionario: Questionnaire, persona: Persona) -> None:
    raw = config_base()
    raw["engine"]["models"] = [{"provider": "fake", "model": "fake-1"}]
    raw["engine"]["nonverbal"] = {"enabled": False}
    cfg = parse_config(raw)
    p = pool()
    client = p.client
    assert isinstance(client, FakeLLMClient)
    result = await run_dialogue(
        spec(persona, Mode.CAPI), questionario, adapt(questionario, Mode.CAPI), p, cfg
    )
    prima = client.requests[0]
    assert prima.schema is not None and "nonverbal" not in prima.schema["properties"]
    assert "nonverbal" not in prima.system
    q1 = by_question(result)[("q1", None)]
    assert q1.nonverbal_emitted is None and q1.nonverbal_observed is None
    assert q1.incongruence is None


async def test_rifiuto(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    result = await run_dialogue(
        spec(persona), questionario, adapt(questionario, Mode.CATI), pool(refuse=True), config
    )
    rec = by_question(result)
    assert rec[("q1", None)].status is AnswerStatus.NONRESPONSE
    assert rec[("q1", None)].item_nonresponse
    assert result.outcome.refusals > 0 and result.outcome.completed
    assert any("rifiuto" in w for w in result.outcome.warnings)


async def test_contesto_limitato(config: SynthSurveyConfig, persona: Persona) -> None:
    raw = {
        "id": "lungo",
        "sections": [
            {
                "id": "s",
                "questions": [
                    {"id": f"q{i}", "text": f"Domanda {i}?", "type": "open"} for i in range(1, 15)
                ],
            }
        ],
    }
    q = parse_questionnaire(raw)
    p = pool()
    client = p.client
    assert isinstance(client, FakeLLMClient)
    await run_dialogue(spec(persona), q, adapt(q, Mode.CATI), p, config)
    ultima = client.requests[-1]
    assert len(ultima.messages) == 17, "8 scambi precedenti più la domanda corrente"
    assert ultima.messages[0].content == "Domanda 6?"


async def test_lettura_con_opzioni_mescolate(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    mq = adapt(questionario, Mode.CATI)
    q2 = mq.question("q2")
    letto = spoken_question(
        q2, ["Trasparenza della bolletta", "Prezzo", "Servizio clienti", "Altro"]
    )
    atteso = "Trasparenza della bolletta; Prezzo; Servizio clienti; Altro."
    assert letto.endswith("Le leggo le possibili risposte: " + atteso)
    assert letto.startswith("Qual è il motivo principale")
    a = await run_dialogue(spec(persona), questionario, mq, pool(), config)
    b = await run_dialogue(spec(persona), questionario, mq, pool(), config)
    assert by_question(a)[("q2", None)].option_order == by_question(b)[("q2", None)].option_order
    assert option_order(q2, None, True) == q2.options


def test_schema_intervistatore_valido() -> None:
    jsonschema.validate(interviewer_reply("probe", utterance="x"), INTERVIEWER_SCHEMA)


async def test_run_interview_instrada_cati_e_capi(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    for mode in (Mode.CATI, Mode.CAPI):
        result = await run_interview(
            spec(persona, mode), questionario, adapt(questionario, mode), pool(), config
        )
        assert result.spec.mode is mode and result.outcome.completed
        assert all(r.mode == mode.value for r in result.records)


RILANCIO = "E l'energia, dove sta in questa lista?"


def con_rilancio(questionario: Questionnaire) -> Questionnaire:
    """Copia del questionario di esempio con un rilancio da copione sulla domanda aperta q7."""
    raw = questionario.model_dump(mode="python")
    for s in raw["sections"]:
        for q in s["questions"]:
            if q["id"] == "q7":
                q["probe"] = RILANCIO
                q["coding_note"] = "Energia citata spontaneamente: sì/no"
    return parse_questionnaire(raw)


async def test_rilancio_da_copione(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    q = con_rilancio(questionario)

    def responder(r: LLMRequest) -> dict[str, Any]:
        assert not is_interviewer(r), "il rilancio da copione non chiama l'agente intervistatore"
        if step(r) == "q:q7:a":
            return respondent_reply(
                r, answer="Più chiarezza in bolletta.", spoken="Più chiarezza in bolletta."
            )
        if step(r) == "q:q7:p":
            assert r.messages[-1].content == RILANCIO and r.messages[-2].role == "assistant"
            return respondent_reply(
                r,
                answer="L'energia pesa, ma non è la prima cosa.",
                spoken="Eh, l'energia pesa, ma non è la prima cosa.",
            )
        return respondent_reply(r)

    result = await run_dialogue(spec(persona), q, adapt(q, Mode.CATI), pool(responder), config)
    q7 = by_question(result)[("q7", None)]
    assert q7.status is AnswerStatus.ANSWERED
    assert q7.answer_text == "Più chiarezza in bolletta.", "la risposta spontanea resta"
    assert q7.probe and q7.probe_text == "L'energia pesa, ma non è la prima cosa."
    turni = [t for t in result.transcript if t.question_id == "q7"]
    assert [t.speaker for t in turni] == [
        "intervistatore",
        "rispondente",
        "intervistatore",
        "rispondente",
    ]
    assert turni[2].text == RILANCIO and turni[3].text.startswith("Eh, l'energia")
    answered = sum(1 for r in result.records if r.status is AnswerStatus.ANSWERED)
    assert result.outcome.calls == answered + 1, "una sola chiamata in più per il rilancio"
    senza = [r for r in result.records if r.question_id != "q7"]
    assert all(not r.probe and r.probe_text is None for r in senza)


async def test_dopo_il_rilancio_niente_approfondimento(
    questionario: Questionnaire, config: SynthSurveyConfig, persona: Persona
) -> None:
    q = con_rilancio(questionario)
    chiamate_i = 0

    def responder(r: LLMRequest) -> dict[str, Any]:
        nonlocal chiamate_i
        if is_interviewer(r):
            chiamate_i += 1
            assert "Rilancio da copione già letto" in r.messages[0].content
            return interviewer_reply("probe", utterance="Vuole aggiungere altro?")
        if step(r) in ("q:q7:a", "q:q7:p"):
            return respondent_reply(r, answer="", spoken="Mah.")
        return respondent_reply(r)

    result = await run_dialogue(spec(persona), q, adapt(q, Mode.CAPI), pool(responder), config)
    q7 = by_question(result)[("q7", None)]
    assert q7.status is AnswerStatus.NONRESPONSE and q7.probe and q7.probe_text == "Mah."
    assert chiamate_i == 1
    turni = [t for t in result.transcript if t.question_id == "q7"]
    assert len(turni) == 4, "l'approfondimento dell'agente dopo il rilancio diventa accettazione"
