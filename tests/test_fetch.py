"""Prebuilt graph archive fetching."""

from __future__ import annotations

import tarfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import scipy.sparse as sp

from hustring.errors import GraphError
from hustring.graph import Graph, fetch_graph_archive


def make_graph(directory: Path) -> None:
    adjacency = sp.csr_matrix(np.array([[0.0, 1.0], [1.0, 0.0]]))
    edges = pd.DataFrame({"a": ["G1"], "b": ["G2"], "weight": [1.0], "source": ["toy"]})
    Graph(["G1", "G2"], ["A", "B"], ["", ""], adjacency, edges, {}).save(directory)


def test_fetch_strips_single_root(tmp_path: Path) -> None:
    make_graph(tmp_path / "graph")
    archive = tmp_path / "graph.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(tmp_path / "graph", arcname="graph")

    dest = tmp_path / "out"
    fetch_graph_archive(archive.as_uri(), dest)

    assert (dest / "adjacency.npz").exists()
    assert Graph.load(dest).n_nodes == 2


def test_fetch_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(GraphError):
        fetch_graph_archive((tmp_path / "nope.tar.gz").as_uri(), tmp_path / "out")


def test_fetch_archive_without_graph_raises(tmp_path: Path) -> None:
    payload = tmp_path / "graph" / "readme.txt"
    payload.parent.mkdir(parents=True)
    payload.write_text("not a graph")
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload, arcname="graph/readme.txt")

    with pytest.raises(GraphError):
        fetch_graph_archive(archive.as_uri(), tmp_path / "out")
