"""Target-centered subnetwork analysis, shared by the CLI and web API."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from .config import RWRConfig
from .core.rwr import rwr
from .core.subgraph import (
    filter_edges,
    induced_edges,
    k_hop_nodes,
    normalize_weights,
    threshold_nodes,
    top_k_nodes,
)
from .errors import SeedError
from .graph.container import Graph

SelectionMode = Literal["top_k", "threshold", "k_hop"]

SOURCE_COLORS: dict[str, str] = {
    "huri": "#ff5d73",
    "string": "#4aa3ff",
    "both": "#a06bff",
    "other": "#8b96ad",
    "unknown": "#8b96ad",
}


def external_links(gene_id: str, symbol: str) -> dict[str, str]:
    """Authoritative lookup URLs for a gene (links out rather than live queries)."""
    query = symbol or gene_id
    return {
        "ensembl": f"https://www.ensembl.org/Gene/Summary?g={gene_id}",
        "ncbi": f"https://www.ncbi.nlm.nih.gov/gene/?term={query}",
        "genecards": f"https://www.genecards.org/cgi-bin/carddisp.pl?gene={query}",
        "uniprot": f"https://www.uniprot.org/uniprotkb?query={query}",
    }


@dataclass(slots=True)
class RankedNode:
    id: str
    symbol: str
    score: float
    source_class: str = "unknown"
    gene_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "score": self.score,
            "source_class": self.source_class,
            "gene_name": self.gene_name,
        }


@dataclass(slots=True)
class SubnetworkResult:
    seeds: list[str]
    resolved_seeds: list[str]
    missing_seeds: list[str]
    seed_ids: list[str]
    mode: SelectionMode
    ranked: list[RankedNode]
    seed_source_classes: list[str] = field(default_factory=list)
    seed_gene_names: list[str] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        seed_nodes = [
            {"id": seed_id, "label": label, "source_class": source_class}
            for seed_id, label, source_class in zip(
                self.seed_ids, self.resolved_seeds, self.seed_source_classes, strict=False
            )
        ]
        return {
            "seeds": self.seeds,
            "resolved_seeds": self.resolved_seeds,
            "missing_seeds": self.missing_seeds,
            "seed_ids": self.seed_ids,
            "seed_nodes": seed_nodes,
            "mode": self.mode,
            "ranked": [node.to_dict() for node in self.ranked],
            "edges": self.edges,
            "parameters": self.parameters,
        }

    def to_cytoscape(self, max_nodes: int = 1500) -> dict[str, Any]:
        """Payload for the browser graph: seed nodes, ranked nodes, and edges."""
        seed_set = set(self.seed_ids)
        nodes: dict[str, dict[str, Any]] = {}
        for index, seed_id in enumerate(self.seed_ids):
            label = self.resolved_seeds[index] if index < len(self.resolved_seeds) else seed_id
            source_class = (
                self.seed_source_classes[index]
                if index < len(self.seed_source_classes)
                else "unknown"
            )
            gene_name = self.seed_gene_names[index] if index < len(self.seed_gene_names) else ""
            nodes[seed_id] = {
                "id": seed_id,
                "label": label,
                "seed": True,
                "source_class": source_class,
                "color": SOURCE_COLORS.get(source_class, SOURCE_COLORS["unknown"]),
                "gene_name": gene_name,
                "links": external_links(seed_id, label),
            }
        for node in self.ranked[:max_nodes]:
            nodes.setdefault(
                node.id,
                {
                    "id": node.id,
                    "label": node.symbol,
                    "seed": node.id in seed_set,
                    "source_class": node.source_class,
                    "color": SOURCE_COLORS.get(node.source_class, SOURCE_COLORS["unknown"]),
                    "gene_name": node.gene_name,
                    "links": external_links(node.id, node.symbol),
                },
            )

        edges: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for edge in self.edges:
            key = (edge["a"], edge["b"])
            if key in seen or edge["a"] not in nodes or edge["b"] not in nodes:
                continue
            seen.add(key)
            edges.append(
                {
                    "id": f"{edge['a']}|{edge['b']}",
                    "source": edge["a"],
                    "target": edge["b"],
                    "weight": edge["weight"],
                }
            )

        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "seed_ids": list(self.seed_ids),
            "missing_seeds": list(self.missing_seeds),
            "mode": self.mode,
            "counts": {
                "nodes": len(self.ranked),
                "edges": len(self.edges),
                "rendered_nodes": len(nodes),
            },
        }


def resolve_seed_indices(
    graph: Graph,
    seeds: Sequence[str],
    weights: Sequence[float] | None = None,
) -> tuple[list[int], list[str], list[str], list[float]]:
    """Resolve seeds by exact node ID first, then by gene symbol."""
    if not seeds:
        raise SeedError("at least one seed is required")
    index_map = graph.index_map()
    symbol_map: dict[str, int] = {}
    for position, symbol in enumerate(graph.symbols):
        symbol_map.setdefault(symbol, position)

    indices: list[int] = []
    resolved: list[str] = []
    missing: list[str] = []
    resolved_weights: list[float] = []
    for position, seed in enumerate(seeds):
        index = index_map.get(seed)
        if index is None:
            index = symbol_map.get(seed)
        if index is None:
            missing.append(seed)
            continue
        indices.append(index)
        resolved.append(seed)
        if weights is not None:
            resolved_weights.append(float(weights[position]))

    if not indices:
        raise SeedError(f"none of the seeds were found in the graph: {list(seeds)}")
    return indices, resolved, missing, resolved_weights


def rank_target_centered(
    graph: Graph,
    seeds: Sequence[str],
    *,
    rwr_config: RWRConfig | None = None,
    mode: SelectionMode = "top_k",
    top_k: int = 50,
    threshold: float | None = None,
    hops: int | None = None,
    exclude_seeds: bool = True,
    include_edges: bool = True,
    min_edge_weight: float | None = None,
    max_edge_weight: float | None = None,
    weight_normalization: str = "none",
    seed_weights: Sequence[float] | None = None,
) -> SubnetworkResult:
    """Run RWR from the seed(s) and extract a target-centered subnetwork.

    Query-time controls (``min_edge_weight``, ``max_edge_weight``,
    ``weight_normalization``, ``seed_weights``) adjust the graph without a rebuild.
    The graph artifact must keep edges below any cutoff you intend to apply.
    """
    cfg = rwr_config or RWRConfig()
    indices, resolved, missing, resolved_weights = resolve_seed_indices(
        graph, seeds, seed_weights
    )
    weights = resolved_weights or None

    if min_edge_weight is not None or max_edge_weight is not None:
        adjacency = filter_edges(graph.adjacency, min_edge_weight, max_edge_weight)
    else:
        adjacency = graph.adjacency.tocsr()
    if weight_normalization and weight_normalization != "none":
        adjacency = normalize_weights(adjacency, weight_normalization)

    scores = rwr(adjacency, indices, weights, config=cfg)
    exclude = indices if exclude_seeds else []

    if mode == "top_k":
        selected = top_k_nodes(scores, top_k, exclude=exclude)
    elif mode == "threshold":
        if threshold is None:
            raise SeedError("threshold mode requires a threshold value")
        selected = threshold_nodes(scores, threshold, exclude=exclude)
    elif mode == "k_hop":
        if hops is None:
            raise SeedError("k_hop mode requires a hop count")
        reached = k_hop_nodes(adjacency, indices, hops)
        reached = np.setdiff1d(reached, np.asarray(exclude, dtype=int))
        selected = reached[np.argsort(-scores[reached])]
    else:
        raise SeedError(f"unknown selection mode '{mode}'")

    ranked = [
        RankedNode(
            id=graph.node_ids[int(i)],
            symbol=graph.symbols[int(i)],
            score=float(scores[int(i)]),
            source_class=graph.source_class_of(graph.node_ids[int(i)]),
            gene_name=graph.gene_name_of(graph.node_ids[int(i)]),
        )
        for i in selected
    ]

    edges: list[dict[str, Any]] = []
    if include_edges and len(selected) > 1:
        row, col, weight = induced_edges(adjacency, selected)
        for a, b, w in zip(row, col, weight, strict=True):
            edges.append(
                {
                    "a": graph.node_ids[int(a)],
                    "b": graph.node_ids[int(b)],
                    "weight": float(w),
                }
            )

    parameters = {
        "restart_prob": cfg.restart_prob,
        "max_iter": cfg.max_iter,
        "tol": cfg.tol,
        "mode": mode,
        "top_k": top_k if mode == "top_k" else None,
        "threshold": threshold if mode == "threshold" else None,
        "hops": hops if mode == "k_hop" else None,
        "exclude_seeds": exclude_seeds,
        "min_edge_weight": min_edge_weight,
        "max_edge_weight": max_edge_weight,
        "weight_normalization": weight_normalization,
        "seed_weights": list(seed_weights) if seed_weights else None,
    }
    return SubnetworkResult(
        seeds=list(seeds),
        resolved_seeds=resolved,
        missing_seeds=missing,
        seed_ids=[graph.node_ids[int(i)] for i in indices],
        seed_source_classes=[graph.source_class_of(graph.node_ids[int(i)]) for i in indices],
        seed_gene_names=[graph.gene_name_of(graph.node_ids[int(i)]) for i in indices],
        mode=mode,
        ranked=ranked,
        edges=edges,
        parameters=parameters,
    )
