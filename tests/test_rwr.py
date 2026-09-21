"""RWR correctness: closed-form check, conservation, localization, edge cases."""

from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

from hustring.config import RWRConfig
from hustring.core.rwr import build_transition_matrix, random_walk_with_restart, rwr
from hustring.errors import ConfigError


def path_adjacency(n: int) -> sp.csr_matrix:
    rows = list(range(n - 1)) + list(range(1, n))
    cols = list(range(1, n)) + list(range(n - 1))
    data = np.ones(len(rows), dtype=np.float64)
    return sp.csr_matrix((data, (rows, cols)), shape=(n, n))


def test_matches_closed_form() -> None:
    adjacency = path_adjacency(6)
    cfg = RWRConfig(restart_prob=0.7, tol=1e-12, max_iter=100_000)
    p0 = np.zeros(6)
    p0[2] = 1.0

    scores = random_walk_with_restart(adjacency, p0, config=cfg)

    transition = build_transition_matrix(adjacency).toarray()
    closed = cfg.restart_prob * np.linalg.solve(
        np.eye(6) - (1.0 - cfg.restart_prob) * transition, p0
    )
    np.testing.assert_allclose(scores, closed, atol=1e-8)


def test_scores_sum_to_one() -> None:
    scores = rwr(path_adjacency(5), [2])
    assert float(scores.sum()) == pytest.approx(1.0)


def test_seed_has_highest_score() -> None:
    scores = rwr(path_adjacency(5), [2])
    assert int(np.argmax(scores)) == 2


def test_higher_restart_localizes() -> None:
    adjacency = path_adjacency(7)
    off_seed = np.array([0, 1, 2, 4, 5, 6])
    low = rwr(adjacency, [3], config=RWRConfig(restart_prob=0.3))
    high = rwr(adjacency, [3], config=RWRConfig(restart_prob=0.95))

    assert high[3] > low[3]
    assert high[off_seed].sum() < low[off_seed].sum()


def test_isolated_seed_retains_mass() -> None:
    adjacency = sp.csr_matrix((np.array([1.0]), (np.array([1]), np.array([0]))), shape=(3, 3))
    scores = rwr(adjacency, [2])
    assert scores[2] == pytest.approx(1.0)


def test_multi_seed_is_symmetric() -> None:
    scores = rwr(path_adjacency(5), [0, 4])
    assert scores[0] == pytest.approx(scores[4])


def test_restart_vector_length_validated() -> None:
    with pytest.raises(ConfigError):
        random_walk_with_restart(path_adjacency(3), [1.0, 0.0])


def test_non_square_adjacency_rejected() -> None:
    with pytest.raises(ConfigError):
        build_transition_matrix(sp.csr_matrix((2, 3)))
