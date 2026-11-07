"""Versioni del questionario per modalità (CAWI, CATI, CAPI).

Regole di adattamento (docs/SPEC.md, "Simulazione delle modalità"):

- CAWI: pagine, tutte le opzioni visibili, "non so" mostrato come opzione,
  griglie intere.
- CATI: una domanda alla volta, opzioni lette ad alta voce, griglie spezzate
  in una domanda per item con la scala ripetuta, "non so" non letto e
  accettato solo se spontaneo, scale lunghe presentate per gli estremi.
- CAPI: come CATI, ma con cartellino per scale e liste lunghe e griglie
  intere sostenute dal cartellino.

L'ordine effettivo delle opzioni per ogni intervista è deciso dal runner con
`option_order`; qui si indica solo se la domanda è randomizzabile.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from synthsurvey.questionnaire.schema import Question, Questionnaire, QuestionType, Scale

DONT_KNOW_LABEL = "Non so / preferisco non rispondere"
CARD_THRESHOLD = 4  # da quante opzioni in su il CAPI usa il cartellino


class Mode(StrEnum):
    CAWI = "cawi"
    CATI = "cati"
    CAPI = "capi"


@dataclass(frozen=True)
class ModeQuestion:
    """Una domanda come viene presentata in una modalità."""

    id: str  # "q5" oppure "q5.a" per un item di griglia spezzata
    source_id: str
    item_id: str | None
    type: QuestionType
    text: str
    options: list[str] | None
    scale: Scale | None
    items: list[tuple[str, str]] | None  # (id, testo) per le griglie intere
    dont_know: bool
    dont_know_visible: bool  # CAWI: opzione mostrata; CATI/CAPI: solo se spontaneo
    read_options: bool  # l'intervistatore legge le opzioni
    show_card: bool  # CAPI: cartellino
    randomize: bool
    fixed_last: list[str]
    page: int | None
    sensitive: bool
    applies_to: list[str] | None
    show_if: str | None
    interviewer_note: str | None = None
    max_choices: int | None = None
    numeric_min: float | None = None
    numeric_max: float | None = None
    unit: str | None = None


@dataclass(frozen=True)
class ModeQuestionnaire:
    mode: Mode
    questionnaire_id: str
    version: str
    questions: list[ModeQuestion]
    pages: dict[int, list[str]] = field(default_factory=dict)  # solo CAWI

    def question(self, qid: str) -> ModeQuestion:
        for q in self.questions:
            if q.id == qid:
                return q
        raise KeyError(qid)


def _scale_text(scale: Scale, *, spoken: bool) -> str:
    """Descrizione della scala: per l'ascolto si leggono solo gli estremi."""
    lo, hi = scale.min, scale.max
    lab_lo, lab_hi = scale.labels.get(lo), scale.labels.get(hi)
    if spoken:
        estremi = ""
        if lab_lo and lab_hi:
            estremi = f", dove {lo} significa «{lab_lo}» e {hi} significa «{lab_hi}»"
        return f"Risponda con un numero da {lo} a {hi}{estremi}."
    etichette = ", ".join(f"{k} = {v}" for k, v in sorted(scale.labels.items()))
    return f"Scala da {lo} a {hi}" + (f" ({etichette})" if etichette else "") + "."


def options_spoken(options: Sequence[str]) -> str:
    return "Le leggo le possibili risposte: " + "; ".join(options) + "."


def _base(q: Question, mode: Mode, text: str, **over: object) -> ModeQuestion:
    spoken = mode in (Mode.CATI, Mode.CAPI)
    fields: dict[str, object] = {
        "id": q.id,
        "source_id": q.id,
        "item_id": None,
        "type": q.type,
        "text": text,
        "options": list(q.options) if q.options else None,
        "scale": q.scale,
        "items": None,
        "dont_know": q.dont_know,
        "dont_know_visible": q.dont_know and mode is Mode.CAWI,
        "read_options": spoken and q.type in (QuestionType.SINGLE, QuestionType.MULTI),
        "show_card": False,
        "randomize": q.randomize,
        "fixed_last": list(q.fixed_last),
        "page": q.page if mode is Mode.CAWI else None,
        "sensitive": q.sensitive,
        "applies_to": q.applies_to,
        "show_if": q.show_if,
        "interviewer_note": None,
        "max_choices": q.max_choices,
        "numeric_min": q.min,
        "numeric_max": q.max,
        "unit": q.unit,
    }
    fields.update(over)
    return ModeQuestion(**fields)  # type: ignore[arg-type]


def _note(q: Question, mode: Mode, extra: list[str]) -> str | None:
    note = list(extra)
    if q.dont_know and mode in (Mode.CATI, Mode.CAPI):
        note.append("Non leggere «non so»: accettarlo solo se spontaneo.")
    if q.sensitive and mode in (Mode.CATI, Mode.CAPI):
        note.append("Domanda sensibile: tono neutro, non insistere.")
    if q.type == QuestionType.MULTI:
        limite = f" (al massimo {q.max_choices})" if q.max_choices else ""
        note.append(f"Risposta multipla{limite}: leggere tutte le opzioni prima di raccogliere.")
    return " ".join(note) if note else None


def _adapt_cawi(q: Question) -> list[ModeQuestion]:
    testo = q.text
    if q.type == QuestionType.SCALE and q.scale:
        testo = f"{q.text} {_scale_text(q.scale, spoken=False)}"
    if q.type == QuestionType.NUMERIC and q.unit:
        testo = f"{q.text} (in {q.unit})"
    items = [(i.id, i.text) for i in q.items] if q.items else None
    return [_base(q, Mode.CAWI, testo, items=items)]


def _adapt_cati(q: Question) -> list[ModeQuestion]:
    if q.type == QuestionType.GRID and q.items:
        out: list[ModeQuestion] = []
        for n, item in enumerate(q.items):
            if q.scale:
                intro = f"{q.text} {_scale_text(q.scale, spoken=True)}" if n == 0 else q.text
                testo = f"{intro} {item.text}."
                note = _note(q, Mode.CATI, [] if n == 0 else ["Ripetere la scala se serve."])
            else:
                testo = f"{q.text} {item.text}. {options_spoken(q.options or [])}"
                note = _note(q, Mode.CATI, [])
            out.append(
                _base(
                    q,
                    Mode.CATI,
                    testo,
                    id=f"{q.id}.{item.id}",
                    item_id=item.id,
                    type=QuestionType.SCALE if q.scale else QuestionType.SINGLE,
                    read_options=q.options is not None,
                    interviewer_note=note,
                    show_if=q.show_if if n == 0 else None,
                )
            )
        return out
    testo = q.text
    if q.type == QuestionType.SCALE and q.scale:
        testo = f"{q.text} {_scale_text(q.scale, spoken=True)}"
    elif q.type in (QuestionType.SINGLE, QuestionType.MULTI) and q.options:
        testo = f"{q.text} {options_spoken(q.options)}"
    elif q.type == QuestionType.NUMERIC and q.unit:
        testo = f"{q.text} Risponda in {q.unit}."
    note = _note(q, Mode.CATI, [])
    return [_base(q, Mode.CATI, testo, interviewer_note=note)]


def _adapt_capi(q: Question) -> list[ModeQuestion]:
    cartellino = (
        q.type == QuestionType.SCALE
        or q.type == QuestionType.GRID
        or (
            q.type in (QuestionType.SINGLE, QuestionType.MULTI)
            and len(q.options or []) > CARD_THRESHOLD
        )
    )
    if q.type == QuestionType.GRID and q.items:
        testo = f"{q.text} (mostrare il cartellino con la scala e leggere ogni affermazione)"
        note = _note(q, Mode.CAPI, ["Cartellino con la scala; una risposta per ogni riga."])
        items = [(i.id, i.text) for i in q.items]
        return [_base(q, Mode.CAPI, testo, items=items, show_card=True, interviewer_note=note)]
    testo = q.text
    extra: list[str] = []
    if cartellino:
        extra.append("Mostrare il cartellino.")
        if q.type == QuestionType.SCALE and q.scale:
            testo = f"{q.text} (cartellino: {_scale_text(q.scale, spoken=False)})"
    elif q.type in (QuestionType.SINGLE, QuestionType.MULTI) and q.options:
        testo = f"{q.text} {options_spoken(q.options)}"
    if q.type == QuestionType.NUMERIC and q.unit:
        testo = f"{q.text} Risponda in {q.unit}."
    note = _note(q, Mode.CAPI, extra)
    return [
        _base(
            q,
            Mode.CAPI,
            testo,
            show_card=cartellino,
            read_options=(q.type in (QuestionType.SINGLE, QuestionType.MULTI)) and not cartellino,
            interviewer_note=note,
        )
    ]


def adapt(questionnaire: Questionnaire, mode: Mode) -> ModeQuestionnaire:
    """Versione del questionario per una modalità."""
    adapters = {Mode.CAWI: _adapt_cawi, Mode.CATI: _adapt_cati, Mode.CAPI: _adapt_capi}
    questions: list[ModeQuestion] = []
    for q in questionnaire.questions:
        questions.extend(adapters[mode](q))
    pages: dict[int, list[str]] = {}
    if mode is Mode.CAWI:
        prossima = 1
        for mq in questions:
            pagina = mq.page if mq.page is not None else prossima
            pages.setdefault(pagina, []).append(mq.id)
            prossima = max(prossima, pagina) + (0 if mq.page is not None else 1)
        pages = dict(sorted(pages.items()))
    return ModeQuestionnaire(
        mode=mode,
        questionnaire_id=questionnaire.id,
        version=questionnaire.version,
        questions=questions,
        pages=pages,
    )


def adapt_all(questionnaire: Questionnaire) -> dict[Mode, ModeQuestionnaire]:
    return {m: adapt(questionnaire, m) for m in Mode}


def option_order(q: ModeQuestion, rng: np.random.Generator | None, randomize: bool) -> list[str]:
    """Ordine di presentazione delle opzioni per una singola intervista.

    Mescola solo se la domanda è randomizzabile, la config lo consente
    (`engine.randomize_option_order`) e c'è un generatore; le voci in
    `fixed_last` restano in coda; il "non so" visibile va per ultimo.
    """
    options = list(q.options or [])
    if randomize and q.randomize and rng is not None:
        mobili = [o for o in options if o not in q.fixed_last]
        fisse = [o for o in options if o in q.fixed_last]
        options = [mobili[i] for i in rng.permutation(len(mobili))] + fisse
    if q.dont_know_visible:
        options.append(DONT_KNOW_LABEL)
    return options
