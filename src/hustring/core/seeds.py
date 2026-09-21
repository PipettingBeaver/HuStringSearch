"""Seed resolution and restart-vector construction.

Resolving user-supplied identifiers is exact-match against canonical node IDs;
symbol/alias resolution happens earlier, in the graph/mapping layer. This keeps
the algorithm core independent of identifier policy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from .._typing import Array
from ..errors import SeedError


@dataclass(frozen=True)
class ResolvedSeeds:
    """Outcome of matching raw seed strings against a graph's node IDs."""

    indices: list[int]
    resolved: list[str]
    missing: list[str]
    weights: list[float] = field(default_factory=list)

    @property
    def n_seeds(self) -> int:
        return len(self.indices)

    @property
    def has_missing(self) -> bool:
        return bool(self.missing)


def resolve_seeds(
    node_ids: Sequence[str],
    seeds: Sequence[str],
    weights: Sequence[float] | None = None,
) -> ResolvedSeeds:
    """Map ``seeds`` to node indices, preserving order and reporting misses."""
    if not seeds:
        raise SeedError("at least one seed is required")
    index_of = {node_id: i for i, node_id in enumerate(node_ids)}
    indices: list[int] = []
    resolved: list[str] = []
    missing: list[str] = []
    resolved_weights: list[float] = []

    for position, seed in enumerate(seeds):
        index = index_of.get(seed)
        if index is None:
            missing.append(seed)
            continue
        indices.append(index)
        resolved.append(seed)
        if weights is not None:
            resolved_weights.append(float(weights[position]))

    if not indices:
        raise SeedError(f"none of the seeds were found in the graph: {list(seeds)}")

    if weights is not None and len(resolved_weights) != len(indices):
        raise SeedError("internal error: weight/seed count mismatch after resolution")

    return ResolvedSeeds(
        indices=indices,
        resolved=resolved,
        missing=missing,
        weights=resolved_weights,
    )


def restart_vector(
    n_nodes: int,
    seed_indices: Sequence[int],
    seed_weights: Sequence[float] | None = None,
) -> Array:
    """Build a normalized restart distribution over ``n_nodes``."""
    if not seed_indices:
        raise SeedError("at least one seed index is required")
    vector = np.zeros(n_nodes, dtype=np.float64)
    if seed_weights is None:
        weight = 1.0 / len(seed_indices)
        for index in seed_indices:
            vector[index] += weight
    else:
        if len(seed_weights) != len(seed_indices):
            raise SeedError("seed weights must match seed indices")
        weights = np.asarray(seed_weights, dtype=np.float64)
        if np.any(weights <= 0):
            raise SeedError("seed weights must be positive")
        weights = weights / weights.sum()
        for index, weight in zip(seed_indices, weights, strict=True):
            vector[index] += float(weight)
    return vector
