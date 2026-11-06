"""IPF generico: margini assoluti, raggruppati, condizionali, zeri strutturali, non convergenza."""

import numpy as np
import pytest

from synthsurvey.population.ipf import ConditionalConstraint, MarginConstraint, aggregate, ipf


def test_due_dimensioni_soluzione_nota() -> None:
    seed = np.ones((2, 2))
    res = ipf(
        seed,
        [
            MarginConstraint(axes=(0,), target=np.array([3.0, 7.0]), name="righe"),
            MarginConstraint(axes=(1,), target=np.array([4.0, 6.0]), name="colonne"),
        ],
    )
    assert res.converged
    np.testing.assert_allclose(res.table.sum(axis=1), [3, 7], rtol=1e-6)
    np.testing.assert_allclose(res.table.sum(axis=0), [4, 6], rtol=1e-6)
    # Con seed uniforme la soluzione è il prodotto dei marginali / totale.
    np.testing.assert_allclose(res.table, np.outer([3, 7], [4, 6]) / 10, rtol=1e-6)
    assert set(res.errors) == {"righe", "colonne"}


def test_margine_raggruppato() -> None:
    seed = np.ones((4, 2))
    gruppi = np.array([0, 0, 1, 1])
    res = ipf(
        seed,
        [
            MarginConstraint(axes=(0,), target=np.array([10.0, 30.0]), groups={0: gruppi}),
            MarginConstraint(axes=(1,), target=np.array([25.0, 15.0])),
        ],
    )
    assert res.converged
    np.testing.assert_allclose(aggregate(res.table, (0,), {0: gruppi}), [10, 30], rtol=1e-6)
    np.testing.assert_allclose(res.table.sum(axis=0), [25, 15], rtol=1e-6)


def test_vincolo_condizionale() -> None:
    seed = np.ones((2, 3))
    shares = np.array([[0.5, 0.3, 0.2], [0.1, 0.1, 0.8]])
    res = ipf(
        seed,
        [
            ConditionalConstraint(axes=(0, 1), cond_axes=(0,), shares=shares),
            MarginConstraint(axes=(0,), target=np.array([100.0, 50.0])),
        ],
    )
    assert res.converged
    np.testing.assert_allclose(res.table.sum(axis=1), [100, 50], rtol=1e-6)
    np.testing.assert_allclose(res.table / res.table.sum(axis=1, keepdims=True), shares, rtol=1e-6)


def test_zeri_strutturali_conservati() -> None:
    seed = np.array([[1.0, 0.0], [1.0, 1.0]])
    res = ipf(
        seed,
        [
            MarginConstraint(axes=(0,), target=np.array([2.0, 8.0])),
            MarginConstraint(axes=(1,), target=np.array([6.0, 4.0])),
        ],
    )
    assert res.converged
    assert res.table[0, 1] == 0.0


def test_margini_incompatibili_non_convergono() -> None:
    res = ipf(
        np.ones((2, 2)),
        [
            MarginConstraint(axes=(0,), target=np.array([3.0, 7.0])),
            MarginConstraint(axes=(1,), target=np.array([5.0, 7.0])),
        ],
        max_iter=50,
    )
    assert not res.converged
    assert res.iterations == 50
    assert res.max_rel_error > 1e-3


def test_errori_di_input() -> None:
    with pytest.raises(ValueError, match="vincoli"):
        ipf(np.ones((2, 2)), [])
    with pytest.raises(ValueError, match="negativi"):
        ipf(np.array([[-1.0, 1.0]]), [MarginConstraint(axes=(0,), target=np.array([1.0]))])


def test_aggregate_ordine_assi() -> None:
    t = np.arange(24, dtype=float).reshape(2, 3, 4)
    a = aggregate(t, (2, 0), {})
    assert a.shape == (2, 4)
    np.testing.assert_allclose(a, t.sum(axis=1))
