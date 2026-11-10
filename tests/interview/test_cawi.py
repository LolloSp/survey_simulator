"""Intervista CAWI con il client finto: pagine, routing, abbandono, rifiuti, seed."""

from typing import Any

import jsonschema

from survey_simulator.config import SurveySimulatorConfig
from survey_simulator.interview import AnswerStatus, InterviewSpec, run_cawi, run_interview
from survey_simulator.interview.cawi import split_groups
from survey_simulator.llm import FakeLLMClient, LLMPool, LLMRequest, fill_schema
from survey_simulator.personas.schema import Persona
from survey_simulator.questionnaire import Mode, Questionnaire, adapt, parse_questionnaire
from tests.interview.conftest import make_persona


def spec(persona: Persona, replicate: int = 1, index: int = 0) -> InterviewSpec:
    return InterviewSpec(
        run_id="test",
        persona=persona,
        persona_index=index,
        mode=Mode.CAWI,
        replicate=replicate,
        model="fake-1",
        seed=42,
    )


def pool(responder: Any = None, **kw: Any) -> LLMPool:
    return LLMPool(FakeLLMClient("fake-1", responder, **kw))


def risposte(request: LLMRequest, **override: Any) -> dict[str, Any]:
    """Riempie lo schema della pagina e sostituisce le risposte indicate."""
    assert request.schema is not None
    out = fill_schema(request.schema)
    out["abandon"] = False
    out["abandon_reason"] = None
    for k, v in override.items():
        if k in out["answers"]:
            out["answers"][k] = v
    return out


def by_question(result: Any) -> dict[tuple[str, str | None], Any]:
    return {(r.question_id, r.item_id): r for r in result.records}


async def test_pilota_predefinito_risponde_a_tutto(
    questionario: Questionnaire, config: SurveySimulatorConfig, persona: Persona
) -> None:
    p = pool(risposte)
    mq = adapt(questionario, Mode.CAWI)
    result = await run_cawi(spec(persona), questionario, mq, p, config)
    rec = by_question(result)
    assert result.outcome.completed and result.outcome.refusals == 0
    # Ogni domanda e item del questionario ha un record, nessuno doppio.
    attese = {(q.id, i.id) for q in questionario.questions if q.items for i in q.items} | {
        (q.id, None) for q in questionario.questions if not q.items
    }
    assert set(rec) == attese and len(result.records) == len(attese)
    # Il client finto sceglie sempre la prima opzione: primacy perfetta.
    assert (
        rec[("q1", None)].answer_code == "1" and rec[("q1", None)].status is AnswerStatus.ANSWERED
    )
    assert rec[("q2", None)].status is AnswerStatus.ANSWERED, "q1 = 1 <= 5 mostra q2"
    assert rec[("q3", None)].answer_text == "Sì, ho cambiato"
    q4 = rec[("q4", None)]
    assert q4.option_order is not None and q4.answer_text == q4.option_order[0], "primacy"
    assert rec[("q5", "a")].answer_code == "1" and rec[("q5", "c")].status is AnswerStatus.ANSWERED
    assert rec[("q7", None)].status is AnswerStatus.ANSWERED, "answered(q1) and q1 <= 7"
    assert rec[("q8", None)].status is AnswerStatus.NOT_APPLICABLE, "solo pmi"
    assert rec[("q9", None)].status is AnswerStatus.NOT_APPLICABLE
    pagine_viste = {r.page for r in result.records if r.page is not None}
    assert result.outcome.calls == len(pagine_viste) and result.outcome.calls >= 4
    assert result.answers["q1"] == 1 and result.answers["q5"] == {"a": 1, "b": 1, "c": 1}
    # I token della chiamata sono ripartiti fra i record della pagina.
    assert sum(r.tokens_in for r in result.records) == result.outcome.tokens_in
    assert sum(r.tokens_out for r in result.records) == result.outcome.tokens_out
    posizioni = [r.position for r in result.records]
    assert sorted(posizioni) == list(range(1, len(posizioni) + 1))


async def test_richieste_al_modello(
    questionario: Questionnaire, config: SurveySimulatorConfig, persona: Persona
) -> None:
    p = pool(risposte)
    client = p.client
    assert isinstance(client, FakeLLMClient)
    await run_cawi(spec(persona), questionario, adapt(questionario, Mode.CAWI), p, config)
    prima = client.requests[0]
    assert "Giulia ha 44 anni" in prima.system and "questionario online" in prima.system
    assert "acquiescenza medio" in prima.system
    assert prima.messages[0].role == "user" and "[q1]" in prima.messages[0].content
    assert "Pagina 1 di" in prima.messages[0].content
    assert prima.effort == config.engine.effort and prima.max_tokens == config.engine.max_tokens
    assert prima.variant == "42:p_00001:cawi:r1:p1g0"
    assert prima.metadata["persona"] == "p_00001"
    jsonschema.validate(risposte(prima), prima.schema)
    seconda = client.requests[1]
    assert [m.role for m in seconda.messages] == ["user", "assistant", "user"]
    assert "[q2]" in seconda.messages[2].content and "[q3]" in seconda.messages[2].content
    assert "Una sola risposta:" in seconda.messages[2].content
    # Il "non so" visibile compare come opzione in coda nelle singole.
    assert "- Non so / preferisco non rispondere" in seconda.messages[2].content


async def test_routing_nasconde_le_domande(
    questionario: Questionnaire, config: SurveySimulatorConfig, persona: Persona
) -> None:
    p = pool(lambda r: risposte(r, q1=9, q3="No"))
    result = await run_cawi(spec(persona), questionario, adapt(questionario, Mode.CAWI), p, config)
    rec = by_question(result)
    assert rec[("q2", None)].status is AnswerStatus.NOT_APPLICABLE, "q1 = 9 > 5"
    assert rec[("q4", None)].status is AnswerStatus.NOT_APPLICABLE, "q3 = No"
    assert rec[("q7", None)].status is AnswerStatus.NOT_APPLICABLE, "q1 > 7"
    assert rec[("q2", None)].answer_code is None and rec[("q2", None)].page is None


async def test_segmento_pmi_vede_le_sue_domande(
    questionario: Questionnaire, config: SurveySimulatorConfig
) -> None:
    pmi = make_persona("p_00002", "pmi")
    p = pool(risposte)
    result = await run_cawi(spec(pmi), questionario, adapt(questionario, Mode.CAWI), p, config)
    rec = by_question(result)
    assert rec[("q8", None)].status is AnswerStatus.ANSWERED
    assert rec[("q9", None)].status is AnswerStatus.ANSWERED
    assert rec[("q8", None)].segment == "pmi"


async def test_dipendenza_nella_stessa_pagina(
    config: SurveySimulatorConfig, persona: Persona
) -> None:
    raw = {
        "id": "pagina",
        "sections": [
            {
                "id": "s",
                "questions": [
                    {"id": "a", "text": "A?", "type": "single", "options": ["x", "y"], "page": 1},
                    {
                        "id": "b",
                        "text": "B?",
                        "type": "single",
                        "options": ["x", "y"],
                        "page": 1,
                        "show_if": 'a == "y"',
                    },
                    {"id": "c", "text": "C?", "type": "open", "page": 1},
                ],
            }
        ],
    }
    q = parse_questionnaire(raw)
    assert split_groups(["a", "b", "c"], q) == [["a"], ["b", "c"]]
    p = pool(lambda r: risposte(r, a="y"))
    result = await run_cawi(spec(persona), q, adapt(q, Mode.CAWI), p, config)
    assert result.outcome.calls == 2
    assert by_question(result)[("b", None)].status is AnswerStatus.ANSWERED
    nascosta = pool(lambda r: risposte(r, a="x"))
    result = await run_cawi(spec(persona), q, adapt(q, Mode.CAWI), nascosta, config)
    assert result.outcome.calls == 2, "c resta visibile anche se b è nascosta"
    assert by_question(result)[("b", None)].status is AnswerStatus.NOT_APPLICABLE


async def test_abbandono(
    questionario: Questionnaire, config: SurveySimulatorConfig, persona: Persona
) -> None:
    def responder(r: LLMRequest) -> dict[str, Any]:
        out = risposte(r)
        if "Pagina 2 di" in r.messages[-1].content:
            out["abandon"] = True
            out["abandon_reason"] = "troppo lungo"
        return out

    p = pool(responder)
    result = await run_cawi(spec(persona), questionario, adapt(questionario, Mode.CAWI), p, config)
    rec = by_question(result)
    assert not result.outcome.completed and result.outcome.abandon_reason == "troppo lungo"
    assert result.outcome.abandoned_at == "q4"
    assert rec[("q1", None)].status is AnswerStatus.ANSWERED
    assert rec[("q2", None)].status is AnswerStatus.ANSWERED, "la pagina 2 viene registrata"
    assert rec[("q4", None)].status is AnswerStatus.ABANDONED
    assert rec[("q5", "b")].status is AnswerStatus.ABANDONED
    assert result.outcome.calls == 2


async def test_rifiuto_e_risposta_non_valida(
    questionario: Questionnaire, config: SurveySimulatorConfig, persona: Persona
) -> None:
    rifiuta = pool(refuse=True)
    result = await run_cawi(
        spec(persona), questionario, adapt(questionario, Mode.CAWI), rifiuta, config
    )
    rec = by_question(result)
    assert result.outcome.refusals >= 1 and result.outcome.completed
    assert rec[("q1", None)].status is AnswerStatus.NONRESPONSE
    assert rec[("q1", None)].item_nonresponse is True
    assert any("rifiuto" in w for w in result.outcome.warnings)
    # Senza q1 il routing nasconde q2 e q7.
    assert rec[("q2", None)].status is AnswerStatus.NOT_APPLICABLE
    testo = pool(lambda r: "non json")
    result = await run_cawi(
        spec(persona), questionario, adapt(questionario, Mode.CAWI), testo, config
    )
    assert by_question(result)[("q1", None)].status is AnswerStatus.NONRESPONSE
    assert any("non valida" in w for w in result.outcome.warnings)


async def test_valori_fuori_schema_diventano_non_risposta(
    questionario: Questionnaire, config: SurveySimulatorConfig, persona: Persona
) -> None:
    p = pool(lambda r: risposte(r, q1=99, q2="Inesistente", q6=-5))
    result = await run_cawi(spec(persona), questionario, adapt(questionario, Mode.CAWI), p, config)
    rec = by_question(result)
    assert rec[("q1", None)].status is AnswerStatus.NONRESPONSE
    assert rec[("q6", None)].status is AnswerStatus.NONRESPONSE
    assert "q1" not in result.answers


async def test_ordine_opzioni_riproducibile(
    questionario: Questionnaire, config: SurveySimulatorConfig, persona: Persona
) -> None:
    mq = adapt(questionario, Mode.CAWI)
    a = await run_cawi(spec(persona), questionario, mq, pool(risposte), config)
    b = await run_cawi(spec(persona), questionario, mq, pool(risposte), config)
    ordine_a = by_question(a)[("q2", None)].option_order
    ordine_b = by_question(b)[("q2", None)].option_order
    assert ordine_a == ordine_b and ordine_a is not None
    assert ordine_a[-1] == "Altro" and set(ordine_a) == set(
        questionario.question("q2").options or []
    )
    # Il "non so" non entra nell'ordine registrato; q3 non randomizza.
    assert by_question(a)[("q3", None)].option_order == questionario.question("q3").options
    diverse = [
        by_question(
            await run_cawi(spec(persona, replicate=r), questionario, mq, pool(risposte), config)
        )[("q4", None)].option_order
        for r in range(1, 6)
    ]
    assert len({tuple(o or []) for o in diverse}) > 1, "repliche diverse, ordini diversi"


async def test_run_interview_instrada_per_modalita(
    questionario: Questionnaire, config: SurveySimulatorConfig, persona: Persona
) -> None:
    mq = adapt(questionario, Mode.CAWI)
    result = await run_interview(spec(persona), questionario, mq, pool(risposte), config)
    assert result.spec.mode is Mode.CAWI and result.records
