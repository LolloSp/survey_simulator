"""Routing del questionario: espressioni `show_if` e domanda successiva.

Linguaggio delle espressioni (valutato senza `eval`):

    q1 <= 5
    q2 == "Prezzo" and not answered(q4)
    q3 in ["Sì, ho cambiato", "No"]
    q4 contains "Passaparola"          (risposta multipla)
    q5.a >= 4                          (item di griglia)
    (q1 > 7 or q6 < 100) and answered(q3)

Una risposta assente, "non so" o non applicabile rende falso ogni confronto
che la riguarda; `answered(q)` è vero solo se c'è una risposta valida.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from survey_simulator.questionnaire.schema import (
    DONT_KNOW_CODE,
    Question,
    Questionnaire,
    QuestionType,
)

Answer = Any  # int | float | str | list[str] | dict[str, Any] | None
Answers = Mapping[str, Answer]


class RoutingError(ValueError):
    """Espressione show_if malformata o incoerente con il questionario."""


# --------------------------------------------------------------------------- #
# Tokenizzazione e parsing
# --------------------------------------------------------------------------- #

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<number>-?\d+(?:\.\d+)?)
  | (?P<op><=|>=|==|!=|<|>)
  | (?P<lparen>\()
  | (?P<rparen>\))
  | (?P<lbracket>\[)
  | (?P<rbracket>\])
  | (?P<comma>,)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)?)
    """,
    re.VERBOSE,
)
KEYWORDS = {"and", "or", "not", "in", "contains", "answered", "true", "false"}


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


def tokenize(text: str) -> list[Token]:
    pos = 0
    out: list[Token] = []
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:
            raise RoutingError(f"carattere inatteso in posizione {pos}: {text[pos]!r}")
        kind = m.lastgroup or ""
        if kind != "ws":
            value = m.group(kind)
            if kind == "ident" and value.lower() in KEYWORDS:
                kind, value = "kw", value.lower()
            out.append(Token(kind, value))
        pos = m.end()
    return out


@dataclass(frozen=True)
class Node:
    kind: str  # and | or | not | cmp | in | contains | answered | const
    children: tuple["Node", ...] = ()
    ref: str | None = None
    op: str | None = None
    value: Any = None


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.t = tokens
        self.i = 0

    def peek(self, kind: str | None = None, value: str | None = None) -> Token | None:
        if self.i >= len(self.t):
            return None
        tok = self.t[self.i]
        if kind is not None and tok.kind != kind:
            return None
        if value is not None and tok.value != value:
            return None
        return tok

    def take(self, kind: str, value: str | None = None) -> Token:
        tok = self.peek(kind, value)
        if tok is None:
            atteso = value or kind
            trovato = self.t[self.i].value if self.i < len(self.t) else "fine espressione"
            raise RoutingError(f"atteso {atteso}, trovato {trovato}")
        self.i += 1
        return tok

    def parse(self) -> Node:
        node = self.or_expr()
        if self.i != len(self.t):
            raise RoutingError(f"testo inatteso dopo l'espressione: {self.t[self.i].value}")
        return node

    def or_expr(self) -> Node:
        node = self.and_expr()
        while self.peek("kw", "or"):
            self.i += 1
            node = Node("or", (node, self.and_expr()))
        return node

    def and_expr(self) -> Node:
        node = self.not_expr()
        while self.peek("kw", "and"):
            self.i += 1
            node = Node("and", (node, self.not_expr()))
        return node

    def not_expr(self) -> Node:
        if self.peek("kw", "not"):
            self.i += 1
            return Node("not", (self.not_expr(),))
        return self.primary()

    def primary(self) -> Node:
        if self.peek("lparen"):
            self.i += 1
            node = self.or_expr()
            self.take("rparen")
            return node
        if self.peek("kw", "answered"):
            self.i += 1
            self.take("lparen")
            ref = self.take("ident").value
            self.take("rparen")
            return Node("answered", ref=ref)
        if self.peek("kw", "true") or self.peek("kw", "false"):
            tok = self.take("kw")
            return Node("const", value=tok.value == "true")
        ref = self.take("ident").value
        if self.peek("kw", "not"):
            self.i += 1
            self.take("kw", "in")
            return Node("not", (Node("in", ref=ref, value=self.list_literal()),))
        if self.peek("kw", "in"):
            self.i += 1
            return Node("in", ref=ref, value=self.list_literal())
        if self.peek("kw", "contains"):
            self.i += 1
            return Node("contains", ref=ref, value=self.literal())
        op = self.take("op").value
        return Node("cmp", ref=ref, op=op, value=self.literal())

    def literal(self) -> Any:
        if self.peek("string"):
            raw = self.take("string").value[1:-1]
            return raw.replace('\\"', '"').replace("\\\\", "\\")
        if self.peek("number"):
            raw = self.take("number").value
            return float(raw) if "." in raw else int(raw)
        if self.peek("kw", "true") or self.peek("kw", "false"):
            return self.take("kw").value == "true"
        trovato = self.t[self.i].value if self.i < len(self.t) else "fine espressione"
        raise RoutingError(f"atteso un valore, trovato {trovato}")

    def list_literal(self) -> list[Any]:
        self.take("lbracket")
        valori: list[Any] = []
        if not self.peek("rbracket"):
            valori.append(self.literal())
            while self.peek("comma"):
                self.i += 1
                valori.append(self.literal())
        self.take("rbracket")
        return valori


def parse(expression: str) -> Node:
    if not expression.strip():
        raise RoutingError("espressione vuota")
    return _Parser(tokenize(expression)).parse()


def references(node: Node) -> set[str]:
    refs: set[str] = set()
    if node.ref is not None:
        refs.add(node.ref)
    for c in node.children:
        refs |= references(c)
    return refs


# --------------------------------------------------------------------------- #
# Valutazione
# --------------------------------------------------------------------------- #


def _lookup(answers: Answers, ref: str) -> Any:
    qid, _, item = ref.partition(".")
    value = answers.get(qid)
    if item:
        value = value.get(item) if isinstance(value, Mapping) else None
    if value == DONT_KNOW_CODE:
        return None
    return value


def _compare(a: Any, op: str, b: Any) -> bool:
    if a is None:
        return False
    if isinstance(a, str) != isinstance(b, str):
        return op == "!="  # tipi diversi: uguali mai, diversi sempre
    if op == "==":
        return bool(a == b)
    if op == "!=":
        return bool(a != b)
    if isinstance(a, str):
        raise RoutingError(f"confronto d'ordine ({op}) fra testi")
    return bool({"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op])


def evaluate(node: Node, answers: Answers) -> bool:
    if node.kind == "const":
        return bool(node.value)
    if node.kind == "and":
        return all(evaluate(c, answers) for c in node.children)
    if node.kind == "or":
        return any(evaluate(c, answers) for c in node.children)
    if node.kind == "not":
        return not evaluate(node.children[0], answers)
    assert node.ref is not None
    value = _lookup(answers, node.ref)
    if node.kind == "answered":
        return value is not None and value != [] and value != ""
    if node.kind == "in":
        return value is not None and value in node.value
    if node.kind == "contains":
        return isinstance(value, list) and node.value in value
    assert node.op is not None
    return _compare(value, node.op, node.value)


# --------------------------------------------------------------------------- #
# Validazione delle espressioni rispetto al questionario
# --------------------------------------------------------------------------- #


def _check_ref(ref: str, q: Question, previous: dict[str, Question]) -> Question:
    qid, _, item = ref.partition(".")
    if qid == q.id:
        raise RoutingError(f"{q.id}: show_if cita la domanda stessa")
    target = previous.get(qid)
    if target is None:
        raise RoutingError(f"{q.id}: show_if cita {qid}, che non è una domanda precedente")
    if item:
        if target.type != QuestionType.GRID:
            raise RoutingError(f"{q.id}: {ref} usa un item ma {qid} non è una griglia")
        if item not in {i.id for i in target.items or []}:
            raise RoutingError(f"{q.id}: item {item} assente nella griglia {qid}")
    elif target.type == QuestionType.GRID:
        raise RoutingError(f"{q.id}: {qid} è una griglia, indicare l'item ({qid}.item)")
    return target


def _check_value(q: Question, node: Node, target: Question) -> None:
    valori = node.value if isinstance(node.value, list) else [node.value]
    is_text = target.type in (QuestionType.SINGLE, QuestionType.MULTI, QuestionType.OPEN) or (
        target.type == QuestionType.GRID and target.options is not None
    )
    for v in valori:
        if is_text:
            if not isinstance(v, str):
                raise RoutingError(f"{q.id}: {target.id} ha risposte testuali, confronto con {v!r}")
            opzioni = target.options
            if opzioni is not None and v not in opzioni:
                raise RoutingError(f"{q.id}: {v!r} non è un'opzione di {target.id}")
        else:
            if isinstance(v, str | bool):
                raise RoutingError(
                    f"{q.id}: {target.id} ha risposte numeriche, confronto con {v!r}"
                )
            scala = target.scale
            if scala is not None and not (scala.min <= v <= scala.max):
                raise RoutingError(f"{q.id}: valore {v} fuori dalla scala di {target.id}")
    if node.kind == "contains" and target.type != QuestionType.MULTI:
        raise RoutingError(f"{q.id}: contains ammesso solo su domande multi ({target.id})")
    if node.kind == "cmp" and node.op in ("<", "<=", ">", ">=") and is_text:
        raise RoutingError(f"{q.id}: confronto d'ordine su risposte testuali di {target.id}")


def validate_show_if(questionnaire: Questionnaire) -> list[str]:
    """Controlla tutte le show_if; restituisce gli errori (vuoto se tutto bene)."""
    errori: list[str] = []
    previous: dict[str, Question] = {}
    for q in questionnaire.questions:
        if q.show_if:
            try:
                node = parse(q.show_if)
                _walk(q, node, previous)
            except RoutingError as exc:
                errori.append(str(exc))
        previous[q.id] = q
    return errori


def _walk(q: Question, node: Node, previous: dict[str, Question]) -> None:
    for c in node.children:
        _walk(q, c, previous)
    if node.ref is not None:
        target = _check_ref(node.ref, q, previous)
        if node.kind in ("cmp", "in", "contains"):
            _check_value(q, node, target)


# --------------------------------------------------------------------------- #
# Percorso del rispondente
# --------------------------------------------------------------------------- #


def applies(q: Question, segment: str) -> bool:
    return q.applies_to is None or segment in q.applies_to


def is_shown(q: Question, answers: Answers) -> bool:
    return q.show_if is None or evaluate(parse(q.show_if), answers)


def next_question(questionnaire: Questionnaire, segment: str, answers: Answers) -> Question | None:
    """Prima domanda non ancora risposta che si applica al segmento e supera la show_if.

    Le domande saltate non compaiono in `answers`; il runner le registra come
    non applicabili.
    """
    for q in questionnaire.questions:
        if q.id in answers or not applies(q, segment):
            continue
        if is_shown(q, answers):
            return q
    return None


def route(questionnaire: Questionnaire, segment: str, answers: Answers) -> list[Question]:
    """Domande che un rispondente con queste risposte avrebbe visto, in ordine."""
    return [q for q in questionnaire.questions if applies(q, segment) and is_shown(q, answers)]
