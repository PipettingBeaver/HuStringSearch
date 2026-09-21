"""Target-centered subnetwork analysis, shared by the CLI and web API."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from .config import RWRConfig
from .core.rwr import rwr
from .core.subgraph import induced_edges, k_hop_nodes, threshold_nodes, top_k_nodes
from .errors import SeedError
from .graph.container import Graph

SelectionMode = Literal["top_k", "threshold", "k_hop"]


@dataclass(slots=True)
class RankedNode:
    id: str
    symbol: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "symbol": self.symbol, "score": self.score}


@dataclass(slots=True)
class SubnetworkResult:
    seeds: list[str]
    resolved_seeds: list[str]
    missing_seeds: list[str]
    seed_ids: list[str]
    mode: SelectionMode
    ranked: list[RankedNode]
    edges: list[dict[str, Any]] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seeds": self.seeds,
            "resolved_seeds": self.resolved_seeds,
            "missing_seeds": self.missing_seeds,
            "seed_ids": self.seed_ids,
            "mode": self.mode,
            "ranked": [node.to_dict() for node in self.ranked],
            "edges": self.edges,
            "parameters": self.parameters,
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
) -> SubnetworkResult:
    """Run RWR from the seed(s) and extract a target-centered subnetwork."""
    cfg = rwr_config or RWRConfig()
    weights = None
    indices, resolved, missing, resolved_weights = resolve_seed_indices(graph, seeds)
    if resolved_weights:
        weights = resolved_weights

    scores = rwr(graph.adjacency, indices, weights or None, config=cfg)
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
        reached = k_hop_nodes(graph.adjacency, indices, hops)
        reached = np.setdiff1d(reached, np.asarray(exclude, dtype=int))
        selected = reached[np.argsort(-scores[reached])]
    else:
        raise SeedError(f"unknown selection mode '{mode}'")

    ranked = [
        RankedNode(id=graph.node_ids[int(i)], symbol=graph.symbols[int(i)], score=float(scores[int(i)]))
        for i in selected
    ]

    edges: list[dict[str, Any]] = []
    if include_edges and len(selected) > 1:
        row, col, weight = induced_edges(graph.adjacency, selected)
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
    }
    return SubnetworkResult(
        seeds=list(seeds),
        resolved_seeds=resolved,
        missing_seeds=missing,
        seed_ids=[graph.node_ids[int(i)] for i in indices],
        mode=mode,
        ranked=ranked,
        edges=edges,
        parameters=parameters,
    )
