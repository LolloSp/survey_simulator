"""Schema Pydantic del questionario sorgente (formato YAML di docs/SPEC.md).

Il questionario è un dato di input: cambia a ogni progetto e il codice non
ne conosce il contenuto. Qui stanno i vincoli strutturali di ogni domanda;
il routing (`show_if`) e il confronto con la configurazione stanno in
`routing.py` e `loader.py`.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DONT_KNOW_CODE = "NS"  # codice di risposta per "non so" / "preferisco non rispondere"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QuestionType(StrEnum):
    SINGLE = "single"
    MULTI = "multi"
    SCALE = "scale"
    GRID = "grid"
    OPEN = "open"
    NUMERIC = "numeric"


class Scale(StrictModel):
    min: int
    max: int
    labels: dict[int, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _coerente(self) -> "Scale":
        if self.max <= self.min:
            raise ValueError(f"scala con max {self.max} non maggiore di min {self.min}")
        if self.max - self.min > 100:
            raise ValueError("scala con più di 101 punti")
        fuori = [k for k in self.labels if k < self.min or k > self.max]
        if fuori:
            raise ValueError(f"etichette fuori dalla scala: {fuori}")
        return self

    @property
    def points(self) -> list[int]:
        return list(range(self.min, self.max + 1))


class GridItem(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    text: str = Field(min_length=1)


class Question(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    text: str = Field(min_length=1)
    type: QuestionType
    options: list[str] | None = None
    max_choices: int | None = Field(default=None, ge=1)
    scale: Scale | None = None
    items: list[GridItem] | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    sensitive: bool = False
    applies_to: list[str] | None = None  # None = tutti i segmenti
    show_if: str | None = None
    dont_know: bool = False
    randomize: bool = False
    fixed_last: list[str] = Field(default_factory=list)
    page: int | None = Field(default=None, ge=1)

    @field_validator("options")
    @classmethod
    def _opzioni(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if not v:
            raise ValueError("options vuoto")
        if any(not o.strip() for o in v):
            raise ValueError("options contiene voci vuote")
        dup = sorted({o for o in v if v.count(o) > 1})
        if dup:
            raise ValueError(f"options con duplicati: {', '.join(dup)}")
        return v

    @field_validator("applies_to")
    @classmethod
    def _segmenti(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and not v:
            raise ValueError("applies_to vuoto: omettere per tutti i segmenti")
        return v

    @model_validator(mode="after")
    def _per_tipo(self) -> "Question":
        t = self.type
        has_options = self.options is not None
        if t in (QuestionType.SINGLE, QuestionType.MULTI):
            if not has_options:
                raise ValueError(f"{t}: servono le options")
            if self.scale is not None or self.items is not None:
                raise ValueError(f"{t}: scale e items non ammessi")
            if len(self.options or []) < 2:
                raise ValueError(f"{t}: servono almeno due opzioni")
        if (
            t == QuestionType.MULTI
            and self.max_choices is not None
            and self.max_choices > len(self.options or [])
        ):
            raise ValueError("max_choices maggiore del numero di opzioni")
        if t != QuestionType.MULTI and self.max_choices is not None:
            raise ValueError("max_choices ammesso solo per multi")
        if t == QuestionType.SCALE:
            if self.scale is None:
                raise ValueError("scale: serve la definizione scale {min, max, labels}")
            if has_options or self.items is not None:
                raise ValueError("scale: options e items non ammessi")
        if t == QuestionType.GRID:
            if not self.items:
                raise ValueError("grid: servono gli items")
            if (self.scale is None) == (self.options is None):
                raise ValueError("grid: serve esattamente uno fra scale e options (colonne)")
            ids = [i.id for i in self.items]
            if len(set(ids)) != len(ids):
                raise ValueError("grid: id degli items duplicati")
        if t == QuestionType.NUMERIC:
            if has_options or self.scale is not None or self.items is not None:
                raise ValueError("numeric: options, scale e items non ammessi")
            if self.min is not None and self.max is not None and self.max <= self.min:
                raise ValueError("numeric: max non maggiore di min")
        if t != QuestionType.NUMERIC and (
            self.min is not None or self.max is not None or self.unit
        ):
            raise ValueError("min, max e unit ammessi solo per numeric")
        if t == QuestionType.OPEN and (
            has_options or self.scale is not None or self.items is not None
        ):
            raise ValueError("open: options, scale e items non ammessi")
        if self.randomize and t not in (QuestionType.SINGLE, QuestionType.MULTI):
            raise ValueError("randomize ammesso solo per single e multi")
        if self.fixed_last:
            if not has_options:
                raise ValueError("fixed_last richiede le options")
            ignote = [o for o in self.fixed_last if o not in (self.options or [])]
            if ignote:
                raise ValueError(
                    f"fixed_last con voci non presenti in options: {', '.join(ignote)}"
                )
        return self

    @property
    def randomizable_options(self) -> list[str]:
        """Opzioni che possono essere mescolate (escluse quelle fisse in coda)."""
        return [o for o in (self.options or []) if o not in self.fixed_last]


class Section(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    title: str | None = None
    questions: list[Question] = Field(min_length=1)


class Questionnaire(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    language: str = Field(default="it", pattern=r"^[a-z]{2}$")
    version: str = "1.0"
    sections: list[Section] = Field(min_length=1)

    @model_validator(mode="after")
    def _id_unici(self) -> "Questionnaire":
        ids = [q.id for s in self.sections for q in s.questions]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ValueError(f"id di domanda duplicati: {', '.join(dup)}")
        sids = [s.id for s in self.sections]
        if len(set(sids)) != len(sids):
            raise ValueError("id di sezione duplicati")
        return self

    @property
    def questions(self) -> list[Question]:
        """Tutte le domande nell'ordine del questionario."""
        return [q for s in self.sections for q in s.questions]

    def question(self, qid: str) -> Question:
        for q in self.questions:
            if q.id == qid:
                return q
        raise KeyError(qid)

    def segments(self) -> set[str]:
        """Segmenti citati in applies_to."""
        return {s for q in self.questions if q.applies_to for s in q.applies_to}
