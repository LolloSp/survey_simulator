"""Pesi di post-stratificazione: raking delle unità sui marginali di popolazione."""

from dataclasses import dataclass

import numpy as np
import polars as pl
from numpy.typing import NDArray

from survey_simulator.population.quotas import QuotaTarget


@dataclass(frozen=True)
class WeightResult:
    weight: NDArray[np.float64]  # somma a n
    weight_pop: NDArray[np.float64]  # somma alla popolazione filtrata
    iterations: int
    max_rel_error: float
    warnings: list[str]

    def summary(self) -> dict[str, float]:
        w = self.weight
        return {
            "min": float(w.min()),
            "median": float(np.median(w)),
            "max": float(w.max()),
            "cv": float(w.std() / w.mean()) if w.mean() > 0 else 0.0,
            "deff": float(len(w) * (w**2).sum() / w.sum() ** 2),
        }


def _rake(
    w: np.ndarray,
    cols: dict[str, np.ndarray],
    attive: list[tuple[str, dict[str, float]]],
    n: int,
    max_iter: int,
    tol: float,
) -> tuple[np.ndarray, int, dict[str, float]]:
    """Raking classico; restituisce pesi, iterazioni e residuo per variabile."""
    w = w.copy()
    residui: dict[str, float] = dict.fromkeys((v for v, _ in attive), 0.0)
    iterations = 0
    while iterations < max_iter:
        iterations += 1
        for var, shares in attive:
            col = cols[var]
            peggiore = 0.0
            for c, share in shares.items():
                mask = col == c
                cur = w[mask].sum()
                tgt = share * n
                if cur > 0:
                    w[mask] *= tgt / cur
                peggiore = max(peggiore, abs(cur - tgt) / n)
            residui[var] = peggiore
        if max(residui.values(), default=0.0) < tol:
            break
    return w, iterations, residui


def rake_weights(
    units: pl.DataFrame,
    targets: list[QuotaTarget],
    population_total: float,
    *,
    max_iter: int = 1000,
    tol: float = 1e-9,
    accept_tol: float = 1e-4,
    extreme_ratio: float = 5.0,
) -> WeightResult:
    """Pesi tali che le distribuzioni pesate delle variabili di quota coincidano con la popolazione.

    Se il raking non converge (campione piccolo e sovracampionamento forte
    rendono i marginali incompatibili), le variabili non sovracampionate con il
    residuo peggiore vengono escluse una alla volta finché i marginali restanti
    sono ricostruiti esattamente. Le categorie con quota di popolazione
    positiva ma senza unità nel campione non possono essere ricostruite:
    vengono segnalate e il loro peso resta ripartito sulle altre.
    """
    n = units.height
    warnings: list[str] = []
    cols = {t.variable: units[t.variable].to_numpy().astype(str) for t in targets}
    attive: list[tuple[str, dict[str, float]]] = []
    for t in targets:
        shares = dict(t.population_shares)
        mancanti = [c for c, s in shares.items() if s > 0 and not (cols[t.variable] == c).any()]
        if mancanti:
            warnings.append(
                f"{t.variable}: nessuna unità per {', '.join(mancanti)}; "
                "i pesi non ricostruiscono quelle categorie"
            )
            for c in mancanti:
                shares[c] = 0.0
            tot = sum(shares.values())
            shares = {c: s / tot for c, s in shares.items()}
        attive.append((t.variable, shares))
    oversampled = {t.variable for t in targets if t.oversampled}

    w = np.ones(n, dtype=np.float64)
    iterations = 0
    residui: dict[str, float] = {}
    escluse: list[str] = []
    while True:
        w, iterations, residui = _rake(np.ones(n), cols, attive, n, max_iter, tol)
        worst = max(residui.values(), default=0.0)
        if worst < tol:
            break
        if worst < accept_tol:
            warnings.append(
                f"raking a convergenza lenta: residuo {worst:.1e} dopo {iterations} iterazioni"
            )
            break
        candidate = [v for v, _ in attive if v not in oversampled]
        if not candidate:
            warnings.append(
                f"raking non convergente (residuo {worst:.3f}) anche sulle sole variabili "
                "sovracampionate: pesi approssimati"
            )
            break
        peggiore = max(candidate, key=lambda v: residui[v])
        escluse.append(f"{peggiore} (residuo {residui[peggiore]:.3f})")
        attive = [(v, s) for v, s in attive if v != peggiore]
        if not attive:
            break
    if escluse:
        warnings.append(
            "marginali incompatibili con il campione: pesi calibrati senza " + ", ".join(escluse)
        )
    w = np.maximum(w, 1e-6)
    w *= n / w.sum()
    # Pesi estremi: rispetto alla mediana dello strato di sovracampionamento,
    # perché fra strati sovracampionati la differenza di peso è voluta.
    if oversampled:
        strato = np.array(["|".join(cols[v][i] for v in sorted(oversampled)) for i in range(n)])
    else:
        strato = np.full(n, "")
    estremi = 0
    for s_ in np.unique(strato):
        mask = strato == s_
        mediana = float(np.median(w[mask]))
        estremi += int((w[mask] > extreme_ratio * mediana).sum())
    if estremi:
        warnings.append(
            f"{estremi} pesi superano {extreme_ratio:g} volte la mediana del proprio strato: "
            "campione sbilanciato rispetto alla popolazione"
        )
    return WeightResult(
        weight=w,
        weight_pop=w * population_total / n,
        iterations=iterations,
        max_rel_error=max(residui.values(), default=0.0),
        warnings=warnings,
    )
