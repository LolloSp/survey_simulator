"""Iterative proportional fitting (raking) su tabelle numpy a più dimensioni.

Due tipi di vincolo:

- `MarginConstraint`: la somma della tabella su alcune assi, eventualmente
  dopo aver raggruppato le categorie di un asse (ad esempio età singole in
  classi), deve valere un target assoluto.
- `ConditionalConstraint`: dentro ogni cella di condizionamento, la
  distribuzione lungo altre assi deve seguire quote date. Il target assoluto
  viene ricalcolato a ogni iterazione dalla massa corrente della cella, così
  fonti con totali diversi (censimento, forze di lavoro) restano coerenti con
  il marginale assoluto della popolazione.
"""

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]


def _one_hot(groups: NDArray[np.int64], n_groups: int) -> Array:
    m = np.zeros((groups.shape[0], n_groups), dtype=np.float64)
    m[np.arange(groups.shape[0]), groups] = 1.0
    return m


def aggregate(table: Array, axes: tuple[int, ...], groups: dict[int, NDArray[np.int64]]) -> Array:
    """Somma `table` sulle assi non in `axes` e raggruppa le assi indicate in `groups`.

    Il risultato ha le assi di `axes` nell'ordine in cui compaiono in `table`.
    """
    keep = tuple(sorted(axes))
    drop = tuple(i for i in range(table.ndim) if i not in keep)
    out = table.sum(axis=drop) if drop else table
    for pos, axis in enumerate(keep):
        if axis in groups:
            g = groups[axis]
            m = _one_hot(g, int(g.max()) + 1)
            out = np.tensordot(out, m, axes=([pos], [0]))
            out = np.moveaxis(out, -1, pos)
    return out


def _expand(
    factor: Array, axes: tuple[int, ...], groups: dict[int, NDArray[np.int64]], ndim: int
) -> Array:
    """Riporta un fattore definito sulle celle aggregate alla forma piena della tabella."""
    keep = tuple(sorted(axes))
    out = factor
    for pos, axis in enumerate(keep):
        if axis in groups:
            out = np.take(out, groups[axis], axis=pos)
    shape = [1] * ndim
    for pos, axis in enumerate(keep):
        shape[axis] = out.shape[pos]
    return out.reshape(shape)


@dataclass(frozen=True)
class MarginConstraint:
    axes: tuple[int, ...]
    target: Array
    groups: dict[int, NDArray[np.int64]] = field(default_factory=dict)
    name: str = ""

    def current(self, table: Array) -> Array:
        return aggregate(table, self.axes, self.groups)

    def target_for(self, table: Array) -> Array:
        return self.target


@dataclass(frozen=True)
class ConditionalConstraint:
    """`shares` ha le assi di `axes` (ordinate come in tabella) e somma a 1 su quelle
    non in `cond_axes` per ogni cella di condizionamento."""

    axes: tuple[int, ...]
    cond_axes: tuple[int, ...]
    shares: Array
    groups: dict[int, NDArray[np.int64]] = field(default_factory=dict)
    name: str = ""

    def current(self, table: Array) -> Array:
        return aggregate(table, self.axes, self.groups)

    def target_for(self, table: Array) -> Array:
        cur = self.current(table)
        keep = tuple(sorted(self.axes))
        free = tuple(i for i, a in enumerate(keep) if a not in self.cond_axes)
        mass = cur.sum(axis=free, keepdims=True)
        return self.shares * mass


Constraint = MarginConstraint | ConditionalConstraint


@dataclass(frozen=True)
class IpfResult:
    table: Array
    iterations: int
    max_rel_error: float
    converged: bool
    errors: dict[str, float]


def _rel_error(current: Array, target: Array) -> float:
    scale = max(float(target.sum()), 1e-12)
    return float(np.abs(current - target).sum() / scale)


def ipf(
    seed: Array,
    constraints: list[Constraint],
    *,
    max_iter: int = 500,
    tol: float = 1e-7,
) -> IpfResult:
    """Adatta `seed` ai vincoli, nell'ordine dato, finché l'errore relativo scende sotto `tol`.

    L'errore di un vincolo è la somma degli scarti assoluti divisa per il totale
    del target; il massimo fra i vincoli deve scendere sotto `tol`. Le celle a
    zero nel seed restano a zero (zeri strutturali).
    """
    if not constraints:
        raise ValueError("servono uno o più vincoli")
    table = np.array(seed, dtype=np.float64)
    if (table < 0).any():
        raise ValueError("il seed non può avere valori negativi")
    errors: dict[str, float] = {}
    iterations = 0
    for iterations in range(1, max_iter + 1):
        for c in constraints:
            cur = c.current(table)
            tgt = c.target_for(table)
            with np.errstate(divide="ignore", invalid="ignore"):
                factor = np.where(cur > 0, tgt / cur, 0.0)
            table = table * _expand(factor, c.axes, c.groups, table.ndim)
        errors = {
            (c.name or f"vincolo_{i}"): _rel_error(c.current(table), c.target_for(table))
            for i, c in enumerate(constraints)
        }
        worst = max(errors.values())
        if worst < tol:
            return IpfResult(table, iterations, worst, True, errors)
    return IpfResult(table, iterations, max(errors.values()), False, errors)
