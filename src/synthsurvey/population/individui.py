"""Popolazione sintetica degli individui (18+): distribuzione congiunta via IPF.

Assi della tabella: regione x sesso x gruppo d'età quinquennale x titolo di
studio x condizione professionale. Il marginale regione x sesso x gruppo
d'età è esatto (popolazione residente); istruzione e condizione seguono le
quote del censimento per regione, sesso e classe d'età. Le Forze di lavoro
entrano come seed: gradiente di istruzione per età dentro le classi censuarie
e associazione istruzione-condizione (vedi docs/methodology.md, §2).
"""

from dataclasses import dataclass

import numpy as np
import polars as pl
from numpy.typing import NDArray

from synthsurvey.population import categories as cat
from synthsurvey.population.ipf import (
    Array,
    ConditionalConstraint,
    Constraint,
    IpfResult,
    MarginConstraint,
    ipf,
)
from synthsurvey.population.istat import codelists as cl
from synthsurvey.population.tables import IstatTables

AGE_MIN = 18

# Gruppi d'età quinquennali interni: (etichetta, età minima, età massima).
AGE_GROUPS: tuple[tuple[str, int, int], ...] = (
    ("18_24", 18, 24),
    ("25_29", 25, 29),
    ("30_34", 30, 34),
    ("35_39", 35, 39),
    ("40_44", 40, 44),
    ("45_49", 45, 49),
    ("50_54", 50, 54),
    ("55_59", 55, 59),
    ("60_64", 60, 64),
    ("65_69", 65, 69),
    ("70_74", 70, 74),
    ("75_79", 75, 79),
    ("80_84", 80, 84),
    ("85_plus", 85, 100),
)
AGE_GROUP_LABELS: tuple[str, ...] = tuple(g[0] for g in AGE_GROUPS)
NO_WORK_AGE = 80  # età da cui il seed esclude occupati e persone in cerca di lavoro

# Assi della tabella congiunta.
AX_REGION, AX_SEX, AX_AGE, AX_EDU, AX_EMP = range(5)
REGION_CODES: tuple[str, ...] = cl.REGION_CODES
SEX: tuple[str, ...] = cat.SEX
EDUCATION: tuple[str, ...] = cat.EDUCATION
EMPLOYMENT: tuple[str, ...] = cat.EMPLOYMENT
SHAPE = (len(REGION_CODES), len(SEX), len(AGE_GROUPS), len(EDUCATION), len(EMPLOYMENT))

# Classi d'età delle fonti, come raggruppamenti dei gruppi quinquennali.
CENSUS_CLASSES: tuple[str, ...] = ("18_24", "25_49", "50_64", "65_plus")
LFS_CLASSES: tuple[str, ...] = ("18_24", "25_34", "35_44", "45_54", "55_64", "65_plus")


def age_group_of(age: int) -> str:
    for label, lo, hi in AGE_GROUPS:
        if lo <= age <= hi:
            return label
    raise ValueError(f"età {age} fuori dai gruppi (>= {AGE_MIN})")


def age_band_of_group(group: str) -> str:
    lo = AGE_GROUPS[AGE_GROUP_LABELS.index(group)][1]
    return cl.age_band(lo)


def _class_index(classes: tuple[str, ...], bounds: dict[str, tuple[int, int]]) -> NDArray[np.int64]:
    """Per ogni gruppo quinquennale, l'indice della classe che lo contiene."""
    idx = []
    for _, lo, hi in AGE_GROUPS:
        trovata = [i for i, c in enumerate(classes) if bounds[c][0] <= lo and hi <= bounds[c][1]]
        if len(trovata) != 1:
            raise AssertionError(f"gruppo {lo}-{hi} non contenuto in una sola classe {classes}")
        idx.append(trovata[0])
    return np.array(idx, dtype=np.int64)


CENSUS_BOUNDS = {"18_24": (18, 24), "25_49": (25, 49), "50_64": (50, 64), "65_plus": (65, 100)}
LFS_BOUNDS = {
    "18_24": (18, 24),
    "25_34": (25, 34),
    "35_44": (35, 44),
    "45_54": (45, 54),
    "55_64": (55, 64),
    "65_plus": (65, 100),
}
CENSUS_GROUP_INDEX = _class_index(CENSUS_CLASSES, CENSUS_BOUNDS)
LFS_GROUP_INDEX = _class_index(LFS_CLASSES, LFS_BOUNDS)


@dataclass(frozen=True)
class IndividuiPopulation:
    table: Array  # SHAPE
    ipf: IpfResult
    ages: Array  # regione x sesso x età singola (0..100), popolazione residente

    def to_frame(self) -> pl.DataFrame:
        """Una riga per cella con attributi e conteggio atteso (`count`)."""
        r, s, a, e, m = np.meshgrid(
            np.arange(SHAPE[0]),
            np.arange(SHAPE[1]),
            np.arange(SHAPE[2]),
            np.arange(SHAPE[3]),
            np.arange(SHAPE[4]),
            indexing="ij",
        )
        codes = [REGION_CODES[i] for i in r.ravel()]
        return pl.DataFrame(
            {
                "region_code": codes,
                "region": [cl.REGIONS[c][0] for c in codes],
                "macro_area": [cl.REGIONS[c][1] for c in codes],
                "sex": [SEX[i] for i in s.ravel()],
                "age_group": [AGE_GROUP_LABELS[i] for i in a.ravel()],
                "age_band": [age_band_of_group(AGE_GROUP_LABELS[i]) for i in a.ravel()],
                "education": [EDUCATION[i] for i in e.ravel()],
                "employment": [EMPLOYMENT[i] for i in m.ravel()],
                "count": self.table.ravel(),
            }
        ).filter(pl.col("count") > 0)


# --------------------------------------------------------------------------- #
# Costruzione dei vincoli
# --------------------------------------------------------------------------- #


def _pivot(
    df: pl.DataFrame, dims: list[tuple[str, tuple[str, ...]]], value: str = "count"
) -> Array:
    """Da tabella lunga a array denso con le assi in `dims` (nome colonna, categorie ordinate)."""
    out = np.zeros([len(c) for _, c in dims], dtype=np.float64)
    index = [{c: i for i, c in enumerate(cats)} for _, cats in dims]
    cols = [df[name].to_list() for name, _ in dims]
    vals = df[value].to_list()
    for k, v in enumerate(vals):
        pos = tuple(index[j][cols[j][k]] for j in range(len(dims)))
        out[pos] += v
    return out


def _shares(counts: Array, axis: int) -> Array:
    tot = counts.sum(axis=axis, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(tot > 0, counts / tot, 0.0)


def _population_by_age(t: IstatTables) -> Array:
    """Regione x sesso x età singola (0..100)."""
    ages = tuple(str(a) for a in range(101))
    df = t.population.with_columns(pl.col("age").cast(pl.String))
    return _pivot(df, [("region_code", REGION_CODES), ("sex", SEX), ("age", ages)])


def _population_by_group(ages: Array) -> Array:
    out = np.zeros((SHAPE[0], SHAPE[1], SHAPE[2]))
    for gi, (_, lo, hi) in enumerate(AGE_GROUPS):
        out[:, :, gi] = ages[:, :, lo : hi + 1].sum(axis=2)
    return out


def _census_education(t: IstatTables, ages: Array) -> Array:
    """Quote di istruzione per regione x sesso x classe censuaria (18+).

    La classe 9-24 del censimento include i 9-17enni, che non possono avere
    un diploma: vengono sottratti dalla categoria `fino_media` usando la
    popolazione residente, così la classe diventa 18-24.
    """
    classi = ("9_24", "25_49", "50_64", "65_plus")
    counts = _pivot(
        t.education,
        [
            ("region_code", REGION_CODES),
            ("sex", SEX),
            ("age_class", classi),
            ("education", EDUCATION),
        ],
    )
    minori = ages[:, :, 9:18].sum(axis=2)
    i_fm = EDUCATION.index("fino_media")
    counts[:, :, 0, i_fm] = np.maximum(counts[:, :, 0, i_fm] - minori, 0.0)
    return _shares(counts, axis=3)


def _census_employment(t: IstatTables, ages: Array) -> Array:
    """Quote di condizione per regione x sesso x classe censuaria (18+).

    La classe 15-24 include i 15-17enni, quasi tutti studenti: vengono sottratti
    da `altro_inattivo`.
    """
    classi = ("15_24", "25_49", "50_64", "65_plus")
    counts = _pivot(
        t.employment,
        [
            ("region_code", REGION_CODES),
            ("sex", SEX),
            ("age_class", classi),
            ("employment", EMPLOYMENT),
        ],
    )
    minori = ages[:, :, 15:18].sum(axis=2)
    i_ai = EMPLOYMENT.index("altro_inattivo")
    counts[:, :, 0, i_ai] = np.maximum(counts[:, :, 0, i_ai] - minori, 0.0)
    return _shares(counts, axis=3)


def _lfs_education(t: IstatTables, ages: Array) -> Array:
    """Quote nazionali di istruzione per sesso x classe decennale (18+).

    La classe 15-24 delle Forze di lavoro include i 15-17enni (tutti
    `fino_media`), sottratti con la popolazione residente nazionale.
    """
    classi = ("15_24", "25_34", "35_44", "45_54", "55_64", "65_89")
    counts = _pivot(
        t.education_national, [("sex", SEX), ("age_class", classi), ("education", EDUCATION)]
    )
    minori = ages[:, :, 15:18].sum(axis=(0, 2))
    i_fm = EDUCATION.index("fino_media")
    counts[:, 0, i_fm] = np.maximum(counts[:, 0, i_fm] - minori, 0.0)
    return _shares(counts, axis=2)


def _lfs_employed_share(t: IstatTables, ages: Array) -> Array:
    """Quota di occupati per sesso x classe decennale x istruzione (nazionale, 18+).

    Occupati / popolazione dalle Forze di lavoro; per la classe 15-24 il
    denominatore `fino_media` viene depurato dei 15-17enni. Restituisce un
    array sesso x classe x istruzione x {occupato, non occupato}.
    """
    classi = ("15_24", "25_34", "35_44", "45_54", "55_64", "65_89")
    pop = _pivot(
        t.education_national, [("sex", SEX), ("age_class", classi), ("education", EDUCATION)]
    )
    occ = _pivot(
        t.employed_national, [("sex", SEX), ("age_class", classi), ("education", EDUCATION)]
    )
    minori = ages[:, :, 15:18].sum(axis=(0, 2))
    i_fm = EDUCATION.index("fino_media")
    pop[:, 0, i_fm] = np.maximum(pop[:, 0, i_fm] - minori, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        share = np.where(pop > 0, np.minimum(occ / pop, 0.98), 0.0)
    return np.stack([share, 1.0 - share], axis=-1)


def build_seed(t: IstatTables, ages: Array) -> Array:
    """Seed dell'IPF dalle Forze di lavoro: gradiente di istruzione per età e associazione
    istruzione-condizione. L'IPF conserva queste interazioni dove i vincoli non le fissano.

    Gli occupati seguono la quota osservata per sesso, classe decennale e titolo;
    le altre tre condizioni si ripartiscono il resto in parti uguali, perché i
    loro livelli vengono poi fissati dal censimento regionale.
    """
    edu = _lfs_education(t, ages)  # sesso x classe LFS x istruzione
    occ = _lfs_employed_share(t, ages)[..., 0]  # sesso x classe LFS x istruzione
    seed = np.ones(SHAPE)
    i_occ = EMPLOYMENT.index("occupato")
    for gi in range(SHAPE[2]):
        ci = LFS_GROUP_INDEX[gi]
        for mi in range(SHAPE[4]):
            quota = occ[:, ci, :] if mi == i_occ else (1.0 - occ[:, ci, :]) / (SHAPE[4] - 1)
            seed[:, :, gi, :, mi] = (edu[:, ci, :] * quota)[np.newaxis, :, :]
    # Oltre i 79 anni nessun occupato né in cerca: le celle a zero nel seed restano a
    # zero nell'IPF, e la quota censuaria dei 65+ si concentra fra i 65 e i 79 anni.
    i_cerca = EMPLOYMENT.index("in_cerca")
    for gi, (_label, lo, _hi) in enumerate(AGE_GROUPS):
        if lo >= NO_WORK_AGE:
            seed[:, :, gi, :, i_occ] = 0.0
            seed[:, :, gi, :, i_cerca] = 0.0
    return seed


def build_constraints(t: IstatTables, ages: Array) -> list[Constraint]:
    """Vincoli dell'IPF: quote censuarie regionali e marginale assoluto della popolazione.

    Le quote di istruzione e condizione sono condizionate alle stesse celle
    (regione x sesso x classe censuaria), quindi sono sempre compatibili fra
    loro e con il marginale: l'IPF converge.
    """
    by_group = _population_by_group(ages)
    return [
        ConditionalConstraint(
            axes=(AX_REGION, AX_SEX, AX_AGE, AX_EDU),
            cond_axes=(AX_REGION, AX_SEX, AX_AGE),
            shares=_census_education(t, ages),
            groups={AX_AGE: CENSUS_GROUP_INDEX},
            name="istruzione_censimento",
        ),
        ConditionalConstraint(
            axes=(AX_REGION, AX_SEX, AX_AGE, AX_EMP),
            cond_axes=(AX_REGION, AX_SEX, AX_AGE),
            shares=_census_employment(t, ages),
            groups={AX_AGE: CENSUS_GROUP_INDEX},
            name="condizione_censimento",
        ),
        # Il marginale assoluto per ultimo: resta esatto a ogni iterazione.
        MarginConstraint(
            axes=(AX_REGION, AX_SEX, AX_AGE), target=by_group, name="popolazione_residente"
        ),
    ]


def build_individui(
    t: IstatTables, *, max_iter: int = 500, tol: float = 1e-7
) -> IndividuiPopulation:
    ages = _population_by_age(t)
    seed = build_seed(t, ages)
    result = ipf(seed, build_constraints(t, ages), max_iter=max_iter, tol=tol)
    return IndividuiPopulation(table=result.table, ipf=result, ages=ages)
