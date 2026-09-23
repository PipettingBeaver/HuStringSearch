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


def test_filter_edges_keeps_band() -> None:
    from hustring.core.subgraph import filter_edges

    adjacency = sp.csr_matrix(
        (
            np.array([0.2, 0.5, 0.9, 0.5, 0.2, 0.9]),
            (
                np.array([0, 1, 2, 0, 1, 2]),
                np.array([1, 2, 0, 2, 0, 1]),
            ),
        ),
        shape=(3, 3),
    )
    filtered = filter_edges(adjacency, min_weight=0.4)
    # only the 0.5 and 0.9 edges remain
    assert sorted(filtered.data.tolist()) == [0.5, 0.5, 0.9, 0.9]


def test_filter_edges_max_bound() -> None:
    from hustring.core.subgraph import filter_edges

    adjacency = sp.csr_matrix(
        (np.array([0.2]), (np.array([0]), np.array([1]))), shape=(2, 2)
    )
    # make it symmetric without summing duplicates
    adjacency = adjacency + adjacency.T
    filtered = filter_edges(adjacency, max_weight=0.5)
    assert filtered.data.tolist() == [0.2, 0.2]


def test_normalize_weights_linear_and_log() -> None:
    from hustring.core.subgraph import normalize_weights

    adjacency = sp.csr_matrix(
        (np.array([1.0, 3.0]), (np.array([0, 1]), np.array([1, 0]))), shape=(2, 2)
    )
    linear = normalize_weights(adjacency, "linear")
    assert sorted(linear.data.tolist()) == [0.0, 1.0]
    logged = normalize_weights(adjacency, "log")
    assert logged.data.max() > logged.data.min()


def test_normalize_weights_none_is_identity() -> None:
    from hustring.core.subgraph import normalize_weights

    adjacency = sp.csr_matrix(
        (np.array([0.3]), (np.array([0]), np.array([1]))), shape=(2, 2)
    )
    same = normalize_weights(adjacency, "none")
    assert same.data.tolist() == [0.3]
