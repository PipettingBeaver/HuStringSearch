"""Merged graph container with save/load for the two-tier data design."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import scipy.sparse as sp

from ..errors import GraphError

NODES_FILE = "nodes.parquet"
EDGES_FILE = "edges.parquet"
ADJACENCY_FILE = "adjacency.npz"
MANIFEST_FILE = "manifest.json"


def derive_node_sources(edges: pd.DataFrame, node_ids: list[str]) -> list[str]:
    """Per-node source membership, derived from the merged edges' ``source`` column."""
    order = {node_id: i for i, node_id in enumerate(node_ids)}
    memberships: list[set[str]] = [set() for _ in node_ids]
    if "source" in edges.columns and not edges.empty:
        a_values = edges["a"].astype(str).tolist()
        b_values = edges["b"].astype(str).tolist()
        source_values = edges["source"].astype(str).tolist()
        for a, b, source in zip(a_values, b_values, source_values, strict=False):
            index_a = order.get(a)
            index_b = order.get(b)
            for part in source.split("|"):
                if not part:
                    continue
                if index_a is not None:
                    memberships[index_a].add(part)
                if index_b is not None:
                    memberships[index_b].add(part)
    return ["|".join(sorted(names)) for names in memberships]


def classify_sources(sources: str) -> str:
    """Map a node's source list to a viewer class: huri / string / both / other."""
    parts = {part for part in sources.split("|") if part}
    has_huri = "huri" in parts
    has_string = "string" in parts
    if has_huri and has_string:
        return "both"
    if has_huri:
        return "huri"
    if has_string:
        return "string"
    if parts:
        return "other"
    return "unknown"



@dataclass(slots=True)
class Graph:
    """A canonical-node weighted graph ready for RWR."""

    node_ids: list[str]
    symbols: list[str]
    descriptions: list[str]
    adjacency: sp.csr_matrix
    edges: pd.DataFrame
    manifest: dict[str, Any] = field(default_factory=dict)
    node_sources: list[str] = field(default_factory=list)
    _index: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        n = len(self.node_ids)
        if self.adjacency.shape != (n, n):
            raise GraphError(
                f"adjacency shape {self.adjacency.shape} does not match {n} nodes"
            )
        if not (len(self.symbols) == n and len(self.descriptions) == n):
            raise GraphError("symbols/descriptions length must match node_ids")
        self._index = {node_id: i for i, node_id in enumerate(self.node_ids)}
        if not self.node_sources:
            self.node_sources = derive_node_sources(self.edges, self.node_ids)
        elif len(self.node_sources) != n:
            raise GraphError("node_sources length must match node_ids")

    @property
    def n_nodes(self) -> int:
        return len(self.node_ids)

    @property
    def n_edges(self) -> int:
        return len(self.edges)

    def index_of(self, node_id: str) -> int | None:
        return self._index.get(node_id)

    def index_map(self) -> dict[str, int]:
        """Return the node-id -> position mapping."""
        return self._index

    def symbol_of(self, node_id: str) -> str:
        index = self._index.get(node_id)
        return self.symbols[index] if index is not None else node_id

    def source_class_of(self, node_id: str) -> str:
        """Viewer class for a node: huri / string / both / other / unknown."""
        index = self._index.get(node_id)
        if index is None:
            return "unknown"
        return classify_sources(self.node_sources[index])

    def summary(self) -> dict[str, Any]:
        return {
            "nodes": self.n_nodes,
            "edges": self.n_edges,
            "manifest": self.manifest,
        }

    def save(self, directory: str | Path) -> Path:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        sp.save_npz(target / ADJACENCY_FILE, self.adjacency.tocsr())
        pd.DataFrame(
            {
                "id": self.node_ids,
                "symbol": self.symbols,
                "description": self.descriptions,
                "sources": self.node_sources,
            }
        ).to_parquet(target / NODES_FILE, index=False)
        self.edges.to_parquet(target / EDGES_FILE, index=False)
        (target / MANIFEST_FILE).write_text(
            json.dumps(self.manifest, indent=2, default=str)
        )
        return target

    @classmethod
    def load(cls, directory: str | Path) -> Graph:
        source = Path(directory)
        if not (source / ADJACENCY_FILE).exists():
            raise GraphError(f"no graph found in {source}")
        adjacency = sp.load_npz(source / ADJACENCY_FILE).tocsr()
        nodes = pd.read_parquet(source / NODES_FILE)
        edges = pd.read_parquet(source / EDGES_FILE)
        manifest_path = source / MANIFEST_FILE
        manifest = (
            json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        )
        node_sources = (
            [str(value) for value in nodes["sources"]] if "sources" in nodes.columns else []
        )
        return cls(
            node_ids=list(nodes["id"]),
            symbols=list(nodes["symbol"]),
            descriptions=list(nodes["description"]),
            adjacency=adjacency,
            edges=edges,
            manifest=manifest,
            node_sources=node_sources,
        )
