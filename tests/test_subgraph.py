"""Subnetwork extraction modes."""

from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

from hustring.core.subgraph import induced_edges, k_hop_nodes, threshold_nodes, top_k_nodes
from hustring.errors import GraphError


def path_adjacency(n: int) -> sp.csr_matrix:
    rows = list(range(n - 1)) + list(range(1, n))
    cols = list(range(1, n)) + list(range(n - 1))
    data = np.ones(len(rows), dtype=np.float64)
    return sp.csr_matrix((data, (rows, cols)), shape=(n, n))


def test_top_k_orders_by_score() -> None:
    scores = np.array([0.1, 0.5, 0.2, 0.9, 0.3])
    assert top_k_nodes(scores, 2).tolist() == [3, 1]


def test_top_k_excludes_seeds() -> None:
    scores = np.array([0.9, 0.5, 0.2])
    assert top_k_nodes(scores, 2, exclude=[0]).tolist() == [1, 2]


def test_top_k_rejects_nonpositive() -> None:
    with pytest.raises(GraphError):
        top_k_nodes(np.array([1.0]), 0)


def test_threshold_filters_and_orders() -> None:
    scores = np.array([0.1, 0.5, 0.2, 0.9])
    assert threshold_nodes(scores, 0.2).tolist() == [3, 1]


def test_k_hop_grows_with_hops() -> None:
    adjacency = path_adjacency(5)
    assert k_hop_nodes(adjacency, [0], 1).tolist() == [0, 1]
    assert k_hop_nodes(adjacency, [0], 2).tolist() == [0, 1, 2]
    assert k_hop_nodes(adjacency, [0], 10).tolist() == [0, 1, 2, 3, 4]


def test_k_hop_negative_hops_rejected() -> None:
    with pytest.raises(GraphError):
        k_hop_nodes(path_adjacency(3), [0], -1)


def test_induced_edges_only_internal() -> None:
    adjacency = path_adjacency(4)
    rows, cols, weights = induced_edges(adjacency, [0, 1, 2])
    pairs = sorted(zip(rows.tolist(), cols.tolist(), weights.tolist(), strict=True))
    assert pairs == [(0, 1, 1.0), (1, 2, 1.0)]
    assert len(weights) == 2
