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


def test_to_cytoscape_payload_shape() -> None:
    result = rank_target_centered(path_graph(), ["G0"], top_k=3)
    payload = result.to_cytoscape()

    ids = {node["id"] for node in payload["nodes"]}
    assert "ENSG0" in ids  # seed always included
    assert payload["seed_ids"] == ["ENSG0"]
    assert any(node["seed"] for node in payload["nodes"])
    assert payload["edges"]
    assert {"id", "source", "target"} <= set(payload["edges"][0])
    assert payload["counts"]["nodes"] == len(result.ranked)
    assert all("color" in node and "source_class" in node for node in payload["nodes"])


def test_min_edge_weight_changes_walk() -> None:
    """A higher cutoff removes weak edges, so the result must change."""
    import pandas as pd
    import scipy.sparse as sp

    from hustring.analysis import rank_target_centered
    from hustring.graph import Graph

    # G0 -- G1 (strong) and G1 -- G2 (weak); G2 is only reachable via the weak edge
    adjacency = sp.csr_matrix(
        np.array([[0.0, 0.9, 0.0], [0.9, 0.0, 0.3], [0.0, 0.3, 0.0]])
    )
    edges = pd.DataFrame(
        {"a": ["G0", "G1"], "b": ["G1", "G2"], "weight": [0.9, 0.3], "source": ["toy", "toy"]}
    )
    graph = Graph(["ENSG0", "ENSG1", "ENSG2"], ["G0", "G1", "G2"], [""] * 3, adjacency, edges, {})

    with_weak = rank_target_centered(graph, ["G0"], top_k=3)
    without_weak = rank_target_centered(graph, ["G0"], top_k=3, min_edge_weight=0.5)

    scores_with = {n.symbol: n.score for n in with_weak.ranked}
    scores_without = {n.symbol: n.score for n in without_weak.ranked}

    # G2 is reachable only through the weak edge, so its score collapses to 0.
    assert scores_with["G2"] > 0
    assert scores_without["G2"] == 0
    assert scores_with["G1"] == scores_without["G1"]
    assert without_weak.parameters["min_edge_weight"] == 0.5


def test_weight_normalization_recorded_in_parameters() -> None:
    result = rank_target_centered(path_graph(), ["G0"], top_k=2, weight_normalization="log")
    assert result.parameters["weight_normalization"] == "log"


def test_seed_weights_reach_parameters() -> None:
    result = rank_target_centered(
        path_graph(), ["G0", "G3"], top_k=1, seed_weights=[3.0, 1.0]
    )
    assert result.parameters["seed_weights"] == [3.0, 1.0]
