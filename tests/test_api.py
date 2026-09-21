"""API tests using FastAPI's TestClient against a small on-disk graph."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from fastapi.testclient import TestClient

from hustring.api.main import create_app
from hustring.graph import Graph


def save_path_graph(directory: Path, n: int = 4) -> None:
    rows = list(range(n - 1)) + list(range(1, n))
    cols = list(range(1, n)) + list(range(n - 1))
    adjacency = sp.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    ids = [f"ENSG{i}" for i in range(n)]
    symbols = [f"G{i}" for i in range(n)]
    edges = pd.DataFrame(
        {"a": ids[:-1], "b": ids[1:], "weight": [1.0] * (n - 1), "source": ["toy"] * (n - 1)}
    )
    Graph(ids, symbols, [""] * n, adjacency, edges, {}).save(directory)


def make_client(graph_dir: Path) -> TestClient:
    return TestClient(create_app(graph_dir=graph_dir, web_dir=graph_dir / "no-web"))


def test_health_reports_graph_present(tmp_path: Path) -> None:
    save_path_graph(tmp_path)
    response = make_client(tmp_path).get("/api/health")
    assert response.status_code == 200
    assert response.json()["graph_present"] is True


def test_summary_and_sources(tmp_path: Path) -> None:
    save_path_graph(tmp_path)
    client = make_client(tmp_path)
    summary = client.get("/api/graph/summary").json()
    assert summary["nodes"] == 4
    names = {entry["name"] for entry in client.get("/api/sources").json()}
    assert {"string", "huri", "biogrid"} <= names


def test_search_finds_symbol(tmp_path: Path) -> None:
    save_path_graph(tmp_path)
    results = make_client(tmp_path).get("/api/search", params={"q": "G1"}).json()
    assert results[0]["symbol"] == "G1"
    assert results[0]["id"] == "ENSG1"


def test_subnetwork_ranks_neighbors(tmp_path: Path) -> None:
    save_path_graph(tmp_path)
    response = make_client(tmp_path).post(
        "/api/subnetwork", json={"seeds": ["G0"], "mode": "top_k", "top_k": 2}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["seed_ids"] == ["ENSG0"]
    assert [node["symbol"] for node in payload["ranked"]] == ["G1", "G2"]


def test_missing_graph_returns_503(tmp_path: Path) -> None:
    client = make_client(tmp_path / "missing")
    assert client.get("/api/graph/summary").status_code == 503


def test_config_descriptions_exposed(tmp_path: Path) -> None:
    save_path_graph(tmp_path)
    descriptions = make_client(tmp_path).get("/api/config/descriptions").json()
    assert "restart_prob" in descriptions["rwr"]
    assert "taxid" in descriptions["build"]
