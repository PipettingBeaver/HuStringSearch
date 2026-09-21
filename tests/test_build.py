"""End-to-end graph build from local sources with an injected resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from hustring.config import BuildConfig, NodeGranularity, SourceConfig, WeightNormalization
from hustring.errors import GraphError
from hustring.graph import build_graph
from hustring.mapping.resolver import IdentifierResolver


def write_edges(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def config_for(path: Path, **overrides: object) -> BuildConfig:
    options: dict[str, object] = {
        "path": str(path),
        "header": 0,
        "a_col": "a",
        "b_col": "b",
        "weight_col": "w",
        "namespace": "toy",
    }
    return BuildConfig(
        sources=[SourceConfig(name="custom", options=options)], **overrides
    )


RESOLVER = IdentifierResolver.from_maps(
    {"toy": {"X": "GX", "Y": "GY", "Z": "GZ", "A": "GA", "B": "GB", "C": "GC", "W": "GW"}}
)


def test_build_maps_dedupes_and_drops_self_loops(tmp_path: Path) -> None:
    path = write_edges(
        tmp_path / "e.tsv",
        "a\tb\tw\nX\tY\t1\nX\tY\t3\nX\tX\t5\nY\tZ\t2\n",
    )
    graph = build_graph(config_for(path), tmp_path, resolver=RESOLVER)

    assert graph.node_ids == ["GX", "GY", "GZ"]
    weights = {
        (row.a, row.b): row.weight
        for row in graph.edges.itertuples(index=False)
    }
    assert weights[("GX", "GY")] == pytest.approx(3.0)
    assert weights[("GY", "GZ")] == pytest.approx(2.0)
    assert ("GX", "GX") not in weights


def test_drop_small_components(tmp_path: Path) -> None:
    path = write_edges(tmp_path / "e.tsv", "a\tb\tw\nX\tY\t1\nA\tB\t1\nB\tC\t1\n")
    graph = build_graph(
        config_for(path, drop_small_components=3), tmp_path, resolver=RESOLVER
    )
    assert graph.node_ids == ["GA", "GB", "GC"]


def test_min_node_degree_filters_leaves(tmp_path: Path) -> None:
    path = write_edges(tmp_path / "e.tsv", "a\tb\tw\nX\tY\t1\nY\tZ\t1\nZ\tW\t1\n")
    graph = build_graph(
        config_for(path, min_node_degree=2), tmp_path, resolver=RESOLVER
    )
    assert graph.node_ids == ["GY", "GZ"]


def test_as_provided_keeps_native_ids(tmp_path: Path) -> None:
    path = write_edges(tmp_path / "e.tsv", "a\tb\tw\nX\tY\t1\n")
    graph = build_graph(
        config_for(path, node_granularity=NodeGranularity.AS_PROVIDED),
        tmp_path,
    )
    assert graph.node_ids == ["X", "Y"]


def test_log_weight_normalization(tmp_path: Path) -> None:
    path = write_edges(tmp_path / "e.tsv", "a\tb\tw\nX\tY\t1\nX\tZ\t3\n")
    graph = build_graph(
        config_for(path, weight_normalization=WeightNormalization.LOG),
        tmp_path,
        resolver=RESOLVER,
    )
    assert sorted(graph.edges["weight"].tolist()) == pytest.approx([0.0, 1.0])


def test_unmapped_edges_are_dropped_and_counted(tmp_path: Path) -> None:
    path = write_edges(tmp_path / "e.tsv", "a\tb\tw\nX\tY\t1\nX\tQ\t1\n")
    graph = build_graph(config_for(path), tmp_path, resolver=RESOLVER)
    assert graph.manifest["unmapped_edges"] == 1
    assert graph.node_ids == ["GX", "GY"]


def test_empty_after_filtering_raises(tmp_path: Path) -> None:
    path = write_edges(tmp_path / "e.tsv", "a\tb\tw\nX\tY\t1\n")
    with pytest.raises(GraphError):
        build_graph(config_for(path, min_node_degree=5), tmp_path, resolver=RESOLVER)
