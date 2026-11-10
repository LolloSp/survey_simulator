"""Modalità CATI e CAPI: dialogo fra intervistatore e rispondente, una domanda alla volta.

Per ogni domanda:

1. l'intervistatore legge la domanda (testo della versione per modalità,
   opzioni nell'ordine deciso dal seed, cartellino nel CAPI);
2. il rispondente (modello) risponde con la battuta a voce, la risposta
   codificata, l'eventuale richiesta di chiarimento e i segnali non verbali;
3. se la domanda ha un rilancio da copione (`probe`), l'intervistatore lo
   legge una sola volta, senza chiamare il modello, e il rispondente parla di
   nuovo: la risposta spontanea resta nel record, quella dopo il rilancio va
   in `probe_text`;
4. l'intervistatore (modello) interviene solo se serve: chiarimento chiesto,
   risposta non codificabile, o segnali osservati forti. Può chiarire o
   approfondire una volta (mai dopo un rilancio da copione), e annota le
   incongruenze fra segnali e parole;
5. dopo un chiarimento o un approfondimento il rispondente parla di nuovo e
   la sua seconda risposta è quella definitiva.

Nella maggior parte delle domande basta una chiamata. L'intervistatore vede
solo i segnali percepibili nella sua modalità (al telefono niente corpo).
"""

from typing import Any

from survey_simulator.config.schema import SurveySimulatorConfig
from survey_simulator.interview.nonverbal import (
    PROBE_THRESHOLD,
    describe_observed,
    max_intensity,
    nonverbal_schema,
    normalize_emitted,
    observe,
)
from survey_simulator.interview.prompting import render_interviewer_system, render_respondent_system
from survey_simulator.interview.records import (
    AnswerStatus,
    AnswerValue,
    code_value,
    is_dont_know,
    routing_value,
    status_for,
    text_value,
)
from survey_simulator.interview.schemas import describe_value, normalize_value, value_schema
from survey_simulator.interview.session import (
    InterviewResult,
    InterviewSpec,
    Turn,
    fill_missing,
    interview_rng,
    new_record,
    variant_for,
)
from survey_simulator.llm.client import LLMRequest, LLMResponse, Message
from survey_simulator.llm.pool import LLMPool
from survey_simulator.questionnaire.modes import (
    DONT_KNOW_LABEL,
    Mode,
    ModeQuestion,
    ModeQuestionnaire,
    option_order,
    options_spoken,
)
from survey_simulator.questionnaire.routing import applies, is_shown
from survey_simulator.questionnaire.schema import Questionnaire, QuestionType

HISTORY_EXCHANGES = 8  # scambi (domanda, risposta) tenuti nel contesto del rispondente
INTERVIEWER_ACTIONS = ("accept", "clarify", "probe")


def respondent_schema(mq: ModeQuestion, presented: list[str], nonverbal: bool) -> dict[str, Any]:
    props: dict[str, Any] = {
        "spoken": {"type": "string"},
        "answer": {"anyOf": [value_schema(mq, presented), {"type": "null"}]},
        "clarification_requested": {"type": "boolean"},
        "clarification": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    }
    if nonverbal:
        props["nonverbal"] = nonverbal_schema(Mode.CATI)
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


INTERVIEWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(INTERVIEWER_ACTIONS)},
        "utterance": {"type": "string"},
        "incongruence": {"type": "boolean"},
        "incongruence_note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["action", "utterance", "incongruence", "incongruence_note"],
    "additionalProperties": False,
}


def spoken_question(mq: ModeQuestion, presented: list[str]) -> str:
    """Testo letto dall'intervistatore, con le opzioni nell'ordine presentato."""
    testo = mq.text
    if mq.read_options and mq.options:
        testo = testo.replace(options_spoken(mq.options), options_spoken(presented))
    if mq.show_card:
        if mq.options:
            testo += " [Cartellino: " + "; ".join(presented) + "]"
        elif mq.scale is not None and "cartellino" not in testo.lower():
            etichette = ", ".join(f"{k} = {v}" for k, v in sorted(mq.scale.labels.items()))
            testo += f" [Cartellino: da {mq.scale.min} a {mq.scale.max}" + (
                f"; {etichette}]" if etichette else "]"
            )
    if mq.type == QuestionType.GRID and mq.items:
        testo += " Affermazioni: " + " ".join(f"({iid}) {t}." for iid, t in mq.items)
    return testo


def _interviewer_brief(
    mq: ModeQuestion,
    utterance: str,
    presented: list[str],
    spoken: str,
    value: AnswerValue,
    clarification: str | None,
    observed: dict[str, Any] | None,
    probed: str | None = None,
) -> str:
    ammesse: str
    if mq.options:
        ammesse = "; ".join(presented) + (
            f"; {DONT_KNOW_LABEL} se spontaneo" if mq.dont_know else ""
        )
    elif mq.scale is not None:
        ammesse = f"numero da {mq.scale.min} a {mq.scale.max}"
    elif mq.type == QuestionType.NUMERIC:
        ammesse = "un numero" + (f" in {mq.unit}" if mq.unit else "")
    else:
        ammesse = "testo libero"
    righe = [
        f"Domanda [{mq.id}]: {utterance}",
        f"Risposte ammesse: {ammesse}",
    ]
    if mq.interviewer_note:
        righe.append(f"Nota per l'intervistatore: {mq.interviewer_note}")
    righe.append(f"Il rispondente ha detto: «{spoken}»")
    righe.append(f"Risposta codificata finora: {describe_value(value)}")
    if clarification:
        righe.append(f"Ha chiesto un chiarimento: «{clarification}»")
    righe.append(f"Segnali percepiti: {describe_observed(observed)}")
    if probed:
        righe.append(
            f"Rilancio da copione già letto: «{probed}». Non approfondire di nuovo: "
            "accettare o chiarire."
        )
    righe.append("Decidi se accettare, chiarire o approfondire.")
    return "\n".join(righe)


def _parse_respondent(
    response: LLMResponse, mq: ModeQuestion, presented: list[str], nonverbal: bool
) -> tuple[str, AnswerValue, bool, str | None, dict[str, Any] | None]:
    parsed = response.parsed if isinstance(response.parsed, dict) else {}
    spoken = parsed.get("spoken")
    spoken = spoken.strip() if isinstance(spoken, str) else ""
    value = normalize_value(mq, parsed.get("answer"), presented)
    chiede = parsed.get("clarification_requested") is True
    clar = parsed.get("clarification")
    clar = clar.strip() if isinstance(clar, str) and clar.strip() else None
    emitted = normalize_emitted(parsed.get("nonverbal")) if nonverbal else None
    return spoken, value, chiede, clar, emitted


async def run_dialogue(
    spec: InterviewSpec,
    questionnaire: Questionnaire,
    mode_questionnaire: ModeQuestionnaire,
    pool: LLMPool,
    config: SurveySimulatorConfig,
) -> InterviewResult:
    mode = spec.mode
    assert mode in (Mode.CATI, Mode.CAPI)
    nonverbal = config.engine.nonverbal.enabled
    rng = interview_rng(spec)
    system_r = render_respondent_system(spec.persona, mode, nonverbal=nonverbal)
    system_i = render_interviewer_system(mode)
    result = InterviewResult(spec)
    outcome = result.outcome
    history: list[Message] = []
    position = 0
    hidden: set[str] = set()
    segment = spec.persona.segment

    def _count(response: LLMResponse) -> None:
        outcome.calls += 1
        outcome.tokens_in += response.usage.input_tokens
        outcome.tokens_out += response.usage.output_tokens
        outcome.latency_ms += response.latency_ms
        outcome.refusals += response.refused

    async def _ask(messages: list[Message], schema: dict[str, Any], step: str) -> LLMResponse:
        request = LLMRequest(
            system=system_r,
            messages=tuple(messages),
            schema=schema,
            max_tokens=config.engine.max_tokens,
            effort=config.engine.effort,
            variant=variant_for(spec, step),
            metadata={
                "persona": spec.persona.persona_id,
                "mode": mode.value,
                "replicate": str(spec.replicate),
                "step": step,
            },
        )
        response = await pool.complete(request)
        _count(response)
        return response

    for mq in mode_questionnaire.questions:
        q = questionnaire.question(mq.source_id)
        if not applies(q, segment) or q.id in hidden:
            continue
        filtro = mq.item_id is None or mq.show_if is not None
        if filtro and not is_shown(q, result.answers):
            hidden.add(q.id)
            continue
        presented = option_order(mq, rng, config.engine.randomize_option_order)
        utterance = spoken_question(mq, presented)
        result.transcript.append(Turn("intervistatore", utterance, question_id=mq.id))
        schema = respondent_schema(mq, presented, nonverbal)
        messages = [*history[-2 * HISTORY_EXCHANGES :], Message("user", utterance)]
        response = await _ask(messages, schema, f"q:{mq.id}:a")
        if response.refused:
            outcome.warnings.append(f"{mq.id}: rifiuto del rispondente")
            position = _record(result, q, mq, None, presented, position, response, nonresponse=True)
            continue
        spoken, value, chiede, clar, emitted = _parse_respondent(response, mq, presented, nonverbal)
        observed = observe(mode, emitted)
        result.transcript.append(
            Turn("rispondente", spoken or "(silenzio)", question_id=mq.id, signals=observed)
        )
        incongruence: bool | None = None
        probe = False
        probe_text: str | None = None
        detto = spoken
        scambio_rilancio: list[Message] = []
        if mq.probe:
            # Rilancio da copione: letto una sola volta, subito dopo la risposta spontanea.
            probe = True
            result.transcript.append(Turn("intervistatore", mq.probe, question_id=mq.id))
            messages = [*messages, Message("assistant", response.text), Message("user", mq.probe)]
            response_p = await _ask(messages, schema, f"q:{mq.id}:p")
            if not response_p.refused:
                spoken_p, value_p, chiede_p, clar_p, emitted_p = _parse_respondent(
                    response_p, mq, presented, nonverbal
                )
                if emitted_p is not None:
                    emitted, observed = emitted_p, observe(mode, emitted_p)
                result.transcript.append(
                    Turn(
                        "rispondente",
                        spoken_p or "(silenzio)",
                        question_id=mq.id,
                        signals=observed,
                    )
                )
                probe_text = text_value(value_p) or spoken_p or None
                detto = f"{spoken} Dopo il rilancio: «{spoken_p}»"
                if value is None and value_p is not None:
                    value = value_p
                if chiede_p:
                    chiede, clar = True, clar_p
                scambio_rilancio = [
                    Message("assistant", response.text),
                    Message("user", mq.probe),
                ]
                response = response_p
        non_codificabile = value is None and not chiede
        forte = max_intensity(observed) >= PROBE_THRESHOLD
        if chiede or non_codificabile or forte:
            brief = _interviewer_brief(
                mq, utterance, presented, detto, value, clar, observed, probed=mq.probe
            )
            request_i = LLMRequest(
                system=system_i,
                messages=(Message("user", brief),),
                schema=INTERVIEWER_SCHEMA,
                max_tokens=min(config.engine.max_tokens, 512),
                effort=config.engine.effort,
                variant=variant_for(spec, f"q:{mq.id}:i"),
                metadata={"persona": spec.persona.persona_id, "mode": mode.value, "role": "i"},
            )
            response_i = await pool.complete(request_i)
            _count(response_i)
            parsed_i = response_i.parsed if isinstance(response_i.parsed, dict) else {}
            action = parsed_i.get("action")
            if action not in INTERVIEWER_ACTIONS:
                action = "clarify" if chiede else "accept"
            if mq.probe and action == "probe":
                action = "accept"  # il rilancio da copione è già stato fatto
            if nonverbal and isinstance(parsed_i.get("incongruence"), bool):
                incongruence = bool(parsed_i["incongruence"])
            battuta = parsed_i.get("utterance")
            battuta = battuta.strip() if isinstance(battuta, str) else ""
            if action in ("clarify", "probe") and (battuta or chiede):
                if not battuta:
                    battuta = "Le rileggo la domanda. " + utterance
                probe = probe or action == "probe"
                result.transcript.append(Turn("intervistatore", battuta, question_id=mq.id))
                messages = [
                    *messages,
                    Message("assistant", response.text),
                    Message("user", battuta),
                ]
                response2 = await _ask(messages, schema, f"q:{mq.id}:b")
                if not response2.refused:
                    spoken2, value2, _, _, emitted2 = _parse_respondent(
                        response2, mq, presented, nonverbal
                    )
                    if value2 is not None:
                        value = value2
                    if action == "probe":
                        probe_text = text_value(value2) or spoken2 or None
                    if emitted2 is not None:
                        emitted, observed = emitted2, observe(mode, emitted2)
                    result.transcript.append(
                        Turn(
                            "rispondente",
                            spoken2 or "(silenzio)",
                            question_id=mq.id,
                            signals=observed,
                        )
                    )
                    response = response2
        history.extend(
            [Message("user", utterance), *scambio_rilancio, Message("assistant", response.text)]
        )
        position = _record(
            result,
            q,
            mq,
            value,
            presented,
            position,
            response,
            clarification=chiede,
            probe=probe,
            probe_text=probe_text,
            emitted=emitted,
            observed=observed,
            incongruence=incongruence,
        )
        if value is not None:
            if mq.item_id is not None:
                griglia = result.answers.setdefault(q.id, {})
                if isinstance(griglia, dict):
                    griglia[mq.item_id] = routing_value(value)
            else:
                result.answers[q.id] = routing_value(value)
    fill_missing(result, questionnaire, AnswerStatus.NOT_APPLICABLE)
    outcome.completed = True
    return result


def _record(
    result: InterviewResult,
    q: Any,
    mq: ModeQuestion,
    value: AnswerValue,
    presented: list[str],
    position: int,
    response: LLMResponse,
    *,
    nonresponse: bool = False,
    clarification: bool = False,
    probe: bool = False,
    probe_text: str | None = None,
    emitted: dict[str, Any] | None = None,
    observed: dict[str, Any] | None = None,
    incongruence: bool | None = None,
) -> int:
    """Record per la domanda adattata: uno per item (griglia intera) o uno solo."""
    spec = result.spec
    ordine = [o for o in presented if o != DONT_KNOW_LABEL] if mq.options else None
    comuni: dict[str, Any] = {
        "option_order": ordine,
        "clarification_requested": clarification,
        "nonverbal_emitted": emitted,
        "nonverbal_observed": observed,
        "incongruence": incongruence,
        "probe": probe,
        "probe_text": probe_text,
        "tokens_in": response.usage.input_tokens,
        "tokens_out": response.usage.output_tokens,
        "latency_ms": response.latency_ms,
    }
    if mq.type == QuestionType.GRID and mq.items:
        celle = value if isinstance(value, dict) else {}
        for iid, _ in mq.items:
            v = celle.get(iid)
            position += 1
            st = status_for(v)
            result.records.append(
                new_record(
                    spec,
                    q,
                    iid,
                    st,
                    position,
                    answer_code=code_value(q, v, iid),
                    answer_text=text_value(v),
                    item_nonresponse=st is AnswerStatus.NONRESPONSE,
                    **comuni,
                )
            )
            comuni = {**comuni, "tokens_in": 0, "tokens_out": 0, "latency_ms": 0}
        return position
    position += 1
    st = status_for(value, open_question=mq.type == QuestionType.OPEN)
    if is_dont_know(value):
        st = AnswerStatus.DONT_KNOW
    result.records.append(
        new_record(
            spec,
            q,
            mq.item_id,
            st,
            position,
            answer_code=code_value(q, value, mq.item_id),
            answer_text=text_value(value),
            item_nonresponse=st is AnswerStatus.NONRESPONSE or nonresponse,
            **comuni,
        )
    )
    return position
