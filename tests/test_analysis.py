"""Target-centered analysis: seed resolution and subnetwork extraction."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from hustring.analysis import rank_target_centered, resolve_seed_indices
from hustring.config import RWRConfig
from hustring.errors import SeedError
from hustring.graph import Graph


def path_graph(n: int = 4) -> Graph:
    rows = list(range(n - 1)) + list(range(1, n))
    cols = list(range(1, n)) + list(range(n - 1))
    data = np.ones(len(rows))
    adjacency = sp.csr_matrix((data, (rows, cols)), shape=(n, n))
    node_ids = [f"ENSG{i}" for i in range(n)]
    symbols = [f"G{i}" for i in range(n)]
    edges = pd.DataFrame(
        {"a": node_ids[:-1], "b": node_ids[1:], "weight": [1.0] * (n - 1), "source": ["toy"] * (n - 1)}
    )
    return Graph(node_ids, symbols, [""] * n, adjacency, edges)


def test_resolve_seeds_by_symbol_and_id() -> None:
    graph = path_graph()
    indices, resolved, missing, _ = resolve_seed_indices(graph, ["ENSG0", "G2", "NOPE"])
    assert indices == [0, 2]
    assert resolved == ["ENSG0", "G2"]
    assert missing == ["NOPE"]


def test_resolve_seeds_all_missing_raises() -> None:
    with pytest.raises(SeedError):
        resolve_seed_indices(path_graph(), ["NOPE"])


def test_top_k_ranks_by_proximity_and_excludes_seed() -> None:
    result = rank_target_centered(path_graph(), ["G0"], top_k=2)
    assert result.mode == "top_k"
    assert [node.symbol for node in result.ranked] == ["G1", "G2"]
    assert result.ranked[0].score > result.ranked[1].score


def test_k_hop_mode_limits_neighborhood() -> None:
    result = rank_target_centered(path_graph(), ["G0"], mode="k_hop", hops=1)
    assert [node.symbol for node in result.ranked] == ["G1"]


def test_threshold_mode_requires_value() -> None:
    with pytest.raises(SeedError):
        rank_target_centered(path_graph(), ["G0"], mode="threshold")


def test_edges_returned_for_selection() -> None:
    result = rank_target_centered(path_graph(), ["G0"], top_k=3)
    assert len(result.edges) >= 2
    assert {"a", "b", "weight"} <= set(result.edges[0])


def test_multi_seed_weights_accepted() -> None:
    result = rank_target_centered(
        path_graph(),
        ["G0", "G3"],
        rwr_config=RWRConfig(restart_prob=0.5),
        top_k=2,
    )
    assert result.resolved_seeds == ["G0", "G3"]
