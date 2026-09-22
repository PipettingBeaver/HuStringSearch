"""Merge sources into one canonical weighted graph, applying BuildConfig."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse import csgraph

from .._typing import Array
from ..config import BuildConfig, DedupePolicy, NodeGranularity, SourceConfig, WeightNormalization
from ..errors import GraphError
from ..mapping.resolver import IdentifierResolver
from ..sources import create_source
from ..sources.base import InteractomeSource, SourceData
from .container import Graph

Annotation = tuple[str | None, str | None, str | None]


def build_graph(
    config: BuildConfig,
    cache_dir: str | Path,
    *,
    force: bool = False,
    resolver: IdentifierResolver | None = None,
    instances: Sequence[InteractomeSource] | None = None,
    enrich_gene_names: bool = False,
) -> Graph:
    """Fetch enabled sources, harmonize IDs, and build the merged graph."""
    cache = Path(cache_dir)
    pairs = _resolve_sources(config, instances)
    if config.node_granularity != NodeGranularity.AS_PROVIDED and resolver is None:
        resolver = IdentifierResolver.from_string(config.taxid, cache / "mapping")

    frames: list[pd.DataFrame] = []
    annotations: dict[str, Annotation] = {}
    source_info: list[dict[str, Any]] = []
    unmapped_total = 0

    for source_config, instance in pairs:
        data = instance.fetch(config.taxid, cache, force=force)
        data.edges = data.edges.assign(
            weight=data.edges["weight"].astype(float) * source_config.weight
        )
        namespace = instance.namespace
        if config.node_granularity == NodeGranularity.AS_PROVIDED:
            edges = data.edges.copy()
        else:
            if resolver is None:
                raise GraphError("identifier mapping required but no resolver available")
            edges, unmapped = resolver.canonicalize(
                data.edges, namespace, strict=config.id_mapping_strict
            )
            unmapped_total += unmapped
        frames.append(edges.assign(source=data.source))
        _collect_annotations(data, namespace, resolver, config.node_granularity, annotations)
        source_info.append(
            {
                "name": data.source,
                "namespace": namespace,
                "edges": len(data.edges),
            }
        )

    if not frames:
        raise GraphError("no sources enabled")
    edges = pd.concat(frames, ignore_index=True)
    if edges.empty:
        raise GraphError("no edges produced by the enabled sources")
    if config.drop_self_loops:
        edges = edges[edges["a"] != edges["b"]]
    edges = _order_pairs(edges)
    edges = _dedupe(edges, config.dedupe_policy)
    if edges.empty:
        raise GraphError("no edges remained after merging")

    node_ids = sorted(pd.unique(pd.concat([edges["a"], edges["b"]])).tolist())
    index = {node_id: i for i, node_id in enumerate(node_ids)}
    adjacency = _adjacency(edges, index, len(node_ids))

    keep = _filter_nodes(adjacency, config)
    if not keep.all():
        adjacency = adjacency[keep][:, keep].tocsr()
        node_ids = [node_id for node_id, keep_it in zip(node_ids, keep, strict=True) if keep_it]
        index = {node_id: i for i, node_id in enumerate(node_ids)}
        edges = edges[edges["a"].isin(index) & edges["b"].isin(index)].reset_index(drop=True)
    if not node_ids:
        raise GraphError("no nodes remained after filtering")

    if enrich_gene_names and config.node_granularity != NodeGranularity.AS_PROVIDED:
        _enrich_gene_names(config.taxid, cache, annotations)

    edges["weight"] = _normalize_weights(edges["weight"], config.weight_normalization)
    adjacency = _adjacency(edges, index, len(node_ids))

    symbols = [annotations.get(node_id, (None, None, None))[0] or node_id for node_id in node_ids]
    gene_names = [
        annotations.get(node_id, (None, None, None))[1] or "" for node_id in node_ids
    ]
    descriptions = [
        annotations.get(node_id, (None, None, None))[2] or "" for node_id in node_ids
    ]
    manifest = {
        "created": datetime.now(timezone.utc).isoformat(),
        "config": config.model_dump(mode="json"),
        "sources": source_info,
        "unmapped_edges": unmapped_total,
        "gene_names": {"enabled": enrich_gene_names, "count": int(bool(gene_names) and sum(bool(n) for n in gene_names))},
        "nodes": len(node_ids),
        "edges": len(edges),
    }
    return Graph(
        node_ids,
        symbols,
        descriptions,
        adjacency,
        edges,
        manifest,
        gene_names=gene_names,
    )


def _resolve_sources(
    config: BuildConfig,
    instances: Sequence[InteractomeSource] | None,
) -> list[tuple[SourceConfig, InteractomeSource]]:
    enabled = config.enabled_sources()
    if instances is not None:
        if len(instances) != len(enabled):
            raise GraphError("instances must match the number of enabled sources")
        return list(zip(enabled, instances, strict=True))
    pairs: list[tuple[SourceConfig, InteractomeSource]] = []
    for source_config in enabled:
        options = dict(source_config.options)
        if source_config.name == "string":
            options.setdefault("min_score", config.string_score_threshold)
        instance = create_source(
            SourceConfig(
                name=source_config.name,
                weight=source_config.weight,
                options=options,
            )
        )
        pairs.append((source_config, instance))
    return pairs


def _enrich_gene_names(
    taxid: int,
    cache: Path,
    annotations: dict[str, Annotation],
) -> None:
    """Best-effort gene-name enrichment; never fails the build."""
    from ..mapping.enrich import fetch_gene_names

    try:
        names = fetch_gene_names(taxid, cache)
    except Exception as exc:
        import warnings

        warnings.warn(f"gene-name enrichment skipped: {exc}", stacklevel=2)
        return
    for gene_id, name in names.items():
        current = annotations.get(gene_id)
        if current is None or not current[1]:
            existing = current or (None, None, None)
            annotations[gene_id] = (existing[0], name, existing[2])


def _collect_annotations(
    data: SourceData,
    namespace: str,
    resolver: IdentifierResolver | None,
    granularity: NodeGranularity,
    annotations: dict[str, Annotation],
) -> None:
    nodes = data.nodes
    if nodes.empty:
        return
    if granularity == NodeGranularity.AS_PROVIDED or namespace == "ensembl_gene":
        canonical = nodes["id"].astype(str)
    elif resolver is not None:
        canonical = resolver.canonical_ids(nodes["id"], namespace)
    else:
        return
    frame = pd.DataFrame(
        {
            "id": canonical,
            "symbol": nodes["symbol"],
            "gene_name": nodes["gene_name"],
            "description": nodes["description"],
        }
    ).dropna(subset=["id"])
    for cid, symbol, gene_name, description in zip(
        frame["id"],
        frame["symbol"],
        frame["gene_name"],
        frame["description"],
        strict=True,
    ):
        current = annotations.get(cid, (None, None, None))
        annotations[cid] = (
            current[0] or (None if pd.isna(symbol) else str(symbol)),
            current[1] or (None if pd.isna(gene_name) else str(gene_name)),
            current[2] or (None if pd.isna(description) else str(description)),
        )


def _order_pairs(edges: pd.DataFrame) -> pd.DataFrame:
    left = edges["a"].to_numpy()
    right = edges["b"].to_numpy()
    swap = left > right
    return edges.assign(a=np.where(swap, right, left), b=np.where(swap, left, right))


def _dedupe(edges: pd.DataFrame, policy: DedupePolicy) -> pd.DataFrame:
    aggregation = {
        DedupePolicy.MAX: "max",
        DedupePolicy.SUM: "sum",
        DedupePolicy.MEAN: "mean",
    }[policy]
    grouped = edges.groupby(["a", "b"], as_index=False).agg(
        weight=("weight", aggregation),
        source=("source", lambda values: "|".join(sorted(set(values)))),
    )
    return grouped


def _adjacency(
    edges: pd.DataFrame,
    index: dict[str, int],
    n_nodes: int,
) -> sp.csr_matrix:
    if edges.empty:
        return sp.csr_matrix((n_nodes, n_nodes))
    row = edges["a"].map(index).to_numpy()
    col = edges["b"].map(index).to_numpy()
    weight = edges["weight"].to_numpy(dtype=float)
    rows = np.concatenate([row, col])
    cols = np.concatenate([col, row])
    data = np.concatenate([weight, weight])
    return sp.csr_matrix((data, (rows, cols)), shape=(n_nodes, n_nodes))


def _filter_nodes(adjacency: sp.csr_matrix, config: BuildConfig) -> Array:
    n_nodes = adjacency.shape[0]
    keep = np.ones(n_nodes, dtype=bool)
    if config.min_node_degree > 0:
        degree = np.asarray(adjacency.getnnz(axis=1)).ravel()
        keep &= degree >= config.min_node_degree
    if (config.drop_small_components > 0 or config.keep_largest_component) and keep.any():
        sub = adjacency[keep][:, keep]
        _, labels = csgraph.connected_components(sub, directed=False)
        sizes = np.bincount(labels) if labels.size else np.array([0])
        if config.keep_largest_component:
            allowed = {int(np.argmax(sizes))}
        else:
            allowed = {i for i, size in enumerate(sizes) if size >= config.drop_small_components}
        component_keep = np.isin(labels, sorted(allowed))
        selected = np.flatnonzero(keep)[component_keep]
        keep = np.zeros(n_nodes, dtype=bool)
        keep[selected] = True
    return keep


def _normalize_weights(weights: pd.Series, mode: WeightNormalization) -> pd.Series:
    values = weights.to_numpy(dtype=float)
    if mode == WeightNormalization.NONE or values.size == 0:
        return pd.Series(values, index=weights.index)
    if mode == WeightNormalization.LOG:
        values = np.log1p(values)
    low, high = float(values.min()), float(values.max())
    if high <= low:
        return pd.Series(np.zeros_like(values), index=weights.index)
    return pd.Series((values - low) / (high - low), index=weights.index)
