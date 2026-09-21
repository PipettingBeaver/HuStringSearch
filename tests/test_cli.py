"""CLI smoke tests via typer's runner."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
from typer.testing import CliRunner

from hustring.cli import app
from hustring.graph import Graph

runner = CliRunner()


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


def test_sources_command_lists_sources() -> None:
    result = runner.invoke(app, ["sources"])
    assert result.exit_code == 0
    assert "huri" in result.stdout
    assert "string" in result.stdout


def test_inspect_command(tmp_path: Path) -> None:
    save_path_graph(tmp_path)
    result = runner.invoke(app, ["inspect", "-g", str(tmp_path)])
    assert result.exit_code == 0
    assert "nodes=4" in result.stdout


def test_walk_command_ranks_subnetwork(tmp_path: Path) -> None:
    save_path_graph(tmp_path)
    result = runner.invoke(app, ["walk", "G0", "-g", str(tmp_path), "--top", "2"])
    assert result.exit_code == 0
    assert "G1" in result.stdout
    assert "mode=top_k" in result.stdout
