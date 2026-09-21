"""Random Walk with Restart on a scipy sparse graph.

Convention: ``restart_prob`` is the probability of returning to the seed
distribution at each step, so the iteration is

    p_{t+1} = (1 - r) * W @ p_t + r * p0

with column-stochastic ``W`` and ``p0`` the (normalized) seed distribution.
Higher ``r`` localizes scores around the seed(s); lower ``r`` diffuses.

The fixed point has the closed form ``p* = r * (I - (1-r) W)^{-1} p0``, which the
tests use as ground truth for the iterative solver.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

import numpy as np
import scipy.sparse as sp

from .._typing import Array
from ..config import RWRConfig
from ..errors import ConfigError

Matrix: TypeAlias = sp.spmatrix


def build_transition_matrix(
    adjacency: Matrix,
    *,
    normalize: bool = True,
    self_loop_isolated: bool = True,
) -> sp.csc_matrix:
    """Build the transition matrix used by the walk.

    With ``normalize`` the result is column-stochastic: each column sums to 1
    (columns of isolated nodes are empty unless ``self_loop_isolated`` adds a
    self-loop so probability cannot leak out).
    """
    if adjacency.shape[0] != adjacency.shape[1]:
        raise ConfigError(f"adjacency must be square, got shape {adjacency.shape}")

    matrix = sp.csr_matrix(adjacency, dtype=np.float64)
    if not normalize:
        return matrix.tocsc()

    col_sums = np.asarray(matrix.sum(axis=0), dtype=np.float64).ravel()
    inv = np.zeros_like(col_sums)
    positive = col_sums > 0
    inv[positive] = 1.0 / col_sums[positive]
    transition = (matrix @ sp.diags(inv)).tocsc()

    if self_loop_isolated:
        isolated = np.flatnonzero(col_sums == 0)
        if isolated.size:
            transition = transition + sp.coo_matrix(
                (np.ones(isolated.size), (isolated, isolated)),
                shape=transition.shape,
            )
            transition = transition.tocsc()
    return transition


def random_walk_with_restart(
    adjacency: Matrix,
    restart_vector: Sequence[float] | Array,
    *,
    config: RWRConfig | None = None,
) -> Array:
    """Return steady-state RWR scores for a prebuilt restart distribution."""
    cfg = config or RWRConfig()
    n = adjacency.shape[0]
    p0: Array = np.asarray(restart_vector, dtype=np.float64).ravel()
    if p0.shape[0] != n:
        raise ConfigError(f"restart vector length {p0.shape[0]} != graph size {n}")
    total = float(p0.sum())
    if total <= 0.0:
        raise ConfigError("restart vector must have positive mass")
    p0 = p0 / total

    transition = build_transition_matrix(
        adjacency,
        normalize=cfg.normalize_columns,
        self_loop_isolated=cfg.self_loop_isolated,
    )
    r = cfg.restart_prob
    scores: Array = p0.copy()
    for _ in range(cfg.max_iter):
        nxt: Array = (1.0 - r) * np.asarray(transition @ scores) + r * p0
        if float(np.abs(nxt - scores).sum()) < cfg.tol:
            return nxt
        scores = nxt
    return scores


def rwr(
    adjacency: Matrix,
    seed_indices: Sequence[int],
    seed_weights: Sequence[float] | None = None,
    *,
    config: RWRConfig | None = None,
) -> Array:
    """Convenience wrapper: build the restart vector from seed indices, then walk."""
    from .seeds import restart_vector

    p0 = restart_vector(adjacency.shape[0], seed_indices, seed_weights)
    return random_walk_with_restart(adjacency, p0, config=config)
