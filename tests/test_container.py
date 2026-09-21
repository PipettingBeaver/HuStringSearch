"""Graph container save/load round-trips."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from hustring.errors import GraphError
from hustring.graph import Graph
from hustring.graph.container import classify_sources, derive_node_sources


def tiny_graph() -> Graph:
    adjacency = sp.csr_matrix(np.array([[0.0, 1.0], [1.0, 0.0]]))
    edges = pd.DataFrame(
        {"a": ["G1"], "b": ["G2"], "weight": [1.0], "source": ["toy"]}
    )
    return Graph(["G1", "G2"], ["A", "B"], ["", ""], adjacency, edges, {"x": 1})


def test_save_load_roundtrip(tmp_path: Path) -> None:
    graph = tiny_graph()
    graph.save(tmp_path)
    loaded = Graph.load(tmp_path)

    assert loaded.node_ids == ["G1", "G2"]
    assert loaded.symbols == ["A", "B"]
    np.testing.assert_allclose(loaded.adjacency.toarray(), graph.adjacency.toarray())
    assert loaded.manifest["x"] == 1
    assert loaded.index_of("G2") == 1
    assert loaded.symbol_of("G1") == "A"


def test_load_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(GraphError):
        Graph.load(tmp_path)


def test_shape_mismatch_rejected() -> None:
    adjacency = sp.csr_matrix((3, 3))
    with pytest.raises(GraphError):
        Graph(["G1"], ["A"], [""], adjacency, pd.DataFrame())


def test_derive_node_sources_and_classification() -> None:
    edges = pd.DataFrame(
        {
            "a": ["G1", "G1", "G2"],
            "b": ["G2", "G3", "G3"],
            "weight": [1.0, 1.0, 1.0],
            "source": ["huri", "huri|string", "string"],
        }
    )
    sources = derive_node_sources(edges, ["G1", "G2", "G3"])
    assert sources == ["huri|string", "huri|string", "huri|string"]
    assert classify_sources("huri") == "huri"
    assert classify_sources("string") == "string"
    assert classify_sources("huri|string") == "both"
    assert classify_sources("") == "unknown"


def test_graph_exposes_source_class_from_edges() -> None:
    adjacency = sp.csr_matrix(np.array([[0.0, 1.0], [1.0, 0.0]]))
    edges = pd.DataFrame(
        {"a": ["G1"], "b": ["G2"], "weight": [1.0], "source": ["huri|string"]}
    )
    graph = Graph(["G1", "G2"], ["A", "B"], ["", ""], adjacency, edges, {})
    assert graph.node_sources == ["huri|string", "huri|string"]
    assert graph.source_class_of("G1") == "both"
    assert graph.source_class_of("missing") == "unknown"
