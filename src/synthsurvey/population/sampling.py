"""Estrazione per quote: campionamento sistematico sulle celle e bilanciamento per scambi.

Il campionamento sistematico sulle celle ordinate per le variabili di quota
dà già marginali vicini ai target; gli scambi successivi spostano singole
unità fra celle finché ogni categoria di ogni variabile di quota coincide con
il target intero. Tutta la casualità passa dal generatore ricevuto.
"""

from dataclasses import dataclass

import numpy as np
import polars as pl
from numpy.typing import NDArray

from synthsurvey.population.quotas import QuotaTarget


@dataclass(frozen=True)
class DrawResult:
    counts: NDArray[np.int64]  # unità estratte per cella (allineato a frame)
    achieved: dict[str, dict[str, int]]
    max_deviation: int
    swaps: int


def _achieved(
    counts: NDArray[np.int64], cols: dict[str, NDArray[np.str_]], targets: list[QuotaTarget]
) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for t in targets:
        col = cols[t.variable]
        out[t.variable] = {c: int(counts[col == c].sum()) for c in t.targets}
    return out


def _score(
    mask: NDArray[np.bool_],
    var: str,
    quota_vars: list[str],
    cols: dict[str, NDArray[np.str_]],
    dev: dict[str, dict[str, int]],
) -> NDArray[np.float64]:
    """Punteggio di una cella: somma degli scarti delle sue categorie nelle altre variabili."""
    s = np.zeros(int(mask.sum()), dtype=np.float64)
    for v in quota_vars:
        if v == var:
            continue
        d = dev[v]
        s += np.array([d[c] for c in cols[v][mask]], dtype=np.float64)
    return s


def draw_cells(
    frame: pl.DataFrame,
    n: int,
    targets: list[QuotaTarget],
    rng: np.random.Generator,
    *,
    max_swaps: int | None = None,
) -> DrawResult:
    """Sceglie quante unità estrarre da ogni cella di `frame` (colonna `count` = peso)."""
    if n <= 0:
        raise ValueError("n deve essere positivo")
    quota_vars = [t.variable for t in targets]
    # Ordine canonico (quote prima, poi tutti gli altri attributi): l'ordine di
    # arrivo del frame non deve influire sul campione.
    altre = [c for c in frame.columns if c not in quota_vars and c != "count"]
    ordered = frame.with_row_index("_row").sort([*quota_vars, *altre])
    w = ordered["count"].to_numpy().astype(np.float64)
    cum = np.cumsum(w)
    total = cum[-1]
    step = total / n
    start = rng.uniform(0.0, step)
    points = start + step * np.arange(n)
    idx = np.searchsorted(cum, points, side="right")
    idx = np.minimum(idx, len(w) - 1)
    counts = np.bincount(idx, minlength=len(w)).astype(np.int64)

    cols = {v: ordered[v].to_numpy().astype(str) for v in quota_vars}
    tgt = {t.variable: t.targets for t in targets}
    swaps = 0
    limit = max_swaps if max_swaps is not None else 50 * n + 100

    def deviations() -> dict[str, dict[str, int]]:
        ach = _achieved(counts, cols, targets)
        return {v: {c: ach[v][c] - tgt[v][c] for c in tgt[v]} for v in quota_vars}

    dev = deviations()
    while swaps < limit:
        var, cat_over, worst = "", "", 0
        for v in quota_vars:
            for c, d in dev[v].items():
                if d > worst:
                    var, cat_over, worst = v, c, d
        if worst == 0:
            break
        cat_under = min(dev[var], key=lambda c: dev[var][c])
        if dev[var][cat_under] >= 0:
            break

        rimuovibili = (cols[var] == cat_over) & (counts > 0)
        aggiungibili = (cols[var] == cat_under) & (w > 0)
        if not rimuovibili.any() or not aggiungibili.any():
            break
        s_rem = _score(rimuovibili, var, quota_vars, cols, dev)
        cand_rem = np.flatnonzero(rimuovibili)[s_rem == s_rem.max()]
        i_rem = int(rng.choice(cand_rem))
        s_add = _score(aggiungibili, var, quota_vars, cols, dev)
        cand_add = np.flatnonzero(aggiungibili)[s_add == s_add.min()]
        p = w[cand_add] / w[cand_add].sum()
        i_add = int(rng.choice(cand_add, p=p))
        counts[i_rem] -= 1
        counts[i_add] += 1
        swaps += 1
        dev = deviations()

    # Riporta i conteggi all'ordine originale del frame.
    back = np.empty_like(counts)
    back[ordered["_row"].to_numpy()] = counts
    final_cols = {v: frame[v].to_numpy().astype(str) for v in quota_vars}
    ach = _achieved(back, final_cols, targets)
    max_dev = max((abs(ach[v][c] - tgt[v][c]) for v in quota_vars for c in tgt[v]), default=0)
    return DrawResult(counts=back, achieved=ach, max_deviation=max_dev, swaps=swaps)


def expand_units(frame: pl.DataFrame, counts: NDArray[np.int64]) -> pl.DataFrame:
    """Una riga per unità estratta, ripetendo le celle secondo `counts`."""
    idx = np.repeat(np.arange(len(counts)), counts)
    return frame.drop("count")[idx.tolist()]
