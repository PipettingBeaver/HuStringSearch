"""Extract a target-centered subnetwork from RWR scores.

Three selection modes are supported and can be combined by callers/UI:
- ``top_k_nodes``: the k highest-scoring nodes.
- ``threshold_nodes``: every node scoring above a cutoff.
- ``k_hop_nodes``: nodes within k hops of the seed(s), ignoring scores.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

import numpy as np
import scipy.sparse as sp

from .._typing import Array
from ..errors import GraphError

Matrix: TypeAlias = sp.spmatrix


def top_k_nodes(
    scores: Array,
    k: int,
    *,
    exclude: Sequence[int] = (),
) -> Array:
    """Indices of the ``k`` highest-scoring nodes (descending score)."""
    if k <= 0:
        raise GraphError("k must be positive")
    values = np.asarray(scores, dtype=np.float64)
    mask = np.ones(values.shape[0], dtype=bool)
    if len(exclude):
        mask[np.asarray(list(exclude), dtype=int)] = False
    candidates = np.flatnonzero(mask)
    if candidates.size <= k:
        return candidates[np.argsort(-values[candidates])]
    partition = np.argpartition(-values[candidates], k)[:k]
    selected = candidates[partition]
    return selected[np.argsort(-values[selected])]


def threshold_nodes(
    scores: Array,
    threshold: float,
    *,
    exclude: Sequence[int] = (),
) -> Array:
    """Indices scoring strictly above ``threshold`` (descending score)."""
    values = np.asarray(scores, dtype=np.float64)
    mask = values > threshold
    if len(exclude):
        mask[np.asarray(list(exclude), dtype=int)] = False
    selected = np.flatnonzero(mask)
    return selected[np.argsort(-values[selected])]


def k_hop_nodes(
    adjacency: Matrix,
    seed_indices: Sequence[int],
    hops: int,
    *,
    undirected: bool = True,
) -> Array:
    """Nodes reachable from the seed(s) within ``hops`` edges."""
    if hops < 0:
        raise GraphError("hops must be >= 0")
    graph = sp.csr_matrix(adjacency)
    if undirected:
        graph = graph.maximum(graph.T).tocsr()
    graph = graph.copy()
    graph.data = np.ones_like(graph.data)

    n = graph.shape[0]
    frontier = np.zeros(n, dtype=bool)
    frontier[np.asarray(list(seed_indices), dtype=int)] = True
    visited = frontier.copy()
    for _ in range(hops):
        reached = np.asarray(graph @ frontier.astype(np.int8)).ravel() > 0
        frontier = reached & ~visited
        if not frontier.any():
            break
        visited |= frontier
    return np.flatnonzero(visited)


def filter_edges(
    adjacency: Matrix,
    min_weight: float | None = None,
    max_weight: float | None = None,
) -> sp.csr_matrix:
    """Return a copy of ``adjacency`` with edges outside the weight band removed."""
    graph = sp.csr_matrix(adjacency)
    if min_weight is None and max_weight is None:
        return graph
    data = graph.data
    keep = np.ones(data.shape[0], dtype=bool)
    if min_weight is not None:
        keep &= data >= min_weight
    if max_weight is not None:
        keep &= data <= max_weight
    graph.data = np.where(keep, data, 0.0)
    graph.eliminate_zeros()
    return graph


def normalize_weights(adjacency: Matrix, mode: str) -> sp.csr_matrix:
    """Rescale edge weights in place by 'none', 'linear', or 'log'."""
    graph = sp.csr_matrix(adjacency)
    if mode in ("none", "", None) or graph.nnz == 0:
        return graph
    data = graph.data
    if mode == "log":
        data = np.log1p(data)
    low, high = float(data.min()), float(data.max())
    if high <= low:
        graph.data = np.zeros_like(data)
    else:
        graph.data = (data - low) / (high - low)
    return graph


def induced_edges(
    adjacency: Matrix,
    nodes: Sequence[int] | Array,
) -> tuple[Array, Array, Array]:
    """Upper-triangular edges (row, col, weight) whose endpoints are both in ``nodes``."""
    graph = sp.csr_matrix(adjacency)
    upper = sp.triu(graph, k=1).tocoo()
    node_set = np.asarray(list(nodes), dtype=int)
    mask = np.isin(upper.row, node_set) & np.isin(upper.col, node_set)
    return (
        upper.row[mask].astype(int),
        upper.col[mask].astype(int),
        upper.data[mask].astype(np.float64),
    )
