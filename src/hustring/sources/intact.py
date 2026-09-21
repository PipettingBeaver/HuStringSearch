"""IntAct source, parsing PSI-MITAB. 

The global IntAct MITAB archive is very large (~1.35 GB), so a local ``path`` or
a species-specific ``url`` is preferred. Columns used (0-based):
0/1 identifiers, 9/10 taxids, 14 confidence values.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from ..errors import SourceError
from .base import (
    DownloadSpec,
    InteractomeSource,
    SourceData,
    SourceMetadata,
    make_edges,
    make_nodes,
)
from .registry import register

GLOBAL_MITAB_URL = (
    "https://ftp.ebi.ac.uk/pub/databases/intact/current/psimitab/intact.zip"
)
TAXID_RE = re.compile(r"taxid:(\d+)")
MISCORE_RE = re.compile(r"intact-miscore:([0-9.]+)")


def _first_id(value: str) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    first = value.split("|")[0]
    if ":" in first:
        prefix, _, rest = first.partition(":")
        if prefix.startswith("chebi"):
            return None
        return rest or None
    return first or None


def _taxid(value: str) -> int | None:
    if not isinstance(value, str):
        return None
    match = TAXID_RE.search(value)
    return int(match.group(1)) if match else None


def _confidence(value: str, default: float) -> float:
    if isinstance(value, str):
        match = MISCORE_RE.search(value)
        if match:
            return float(match.group(1))
    return default


def parse_intact(
    path: Path,
    taxid: int,
    *,
    keep_other_species: bool = False,
    default_weight: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse an IntAct PSI-MITAB file, filtered to ``taxid``."""
    frame = pd.read_csv(
        path,
        sep="\t",
        header=None,
        dtype=str,
        usecols=[0, 1, 9, 10, 14],
        names=["id_a", "id_b", "taxid_a", "taxid_b", "confidence"],
        compression="infer",
        low_memory=False,
    )
    frame["taxid_a"] = frame["taxid_a"].map(_taxid)
    frame["taxid_b"] = frame["taxid_b"].map(_taxid)
    if keep_other_species:
        mask = (frame["taxid_a"] == taxid) | (frame["taxid_b"] == taxid)
    else:
        mask = (frame["taxid_a"] == taxid) & (frame["taxid_b"] == taxid)
    frame = frame[mask]

    frame["a"] = frame["id_a"].map(_first_id)
    frame["b"] = frame["id_b"].map(_first_id)
    frame["weight"] = frame["confidence"].map(lambda v: _confidence(v, default_weight))
    frame = frame.dropna(subset=["a", "b"])
    edges = make_edges(frame[["a", "b", "weight"]])
    nodes = make_nodes(pd.DataFrame({"id": pd.unique(pd.concat([frame["a"], frame["b"]]))}))
    return edges, nodes


@register
class IntactSource(InteractomeSource):
    metadata = SourceMetadata(
        name="intact",
        display_name="IntAct",
        namespace="uniprot",
        version="current",
        supported_taxids=None,
        directed=False,
        default_weight=1.0,
        citation="Del Toro et al., Nucleic Acids Research (2022)",
        homepage="https://www.ebi.ac.uk/intact",
        notes=(
            "Prefers a local PSI-MITAB file or species-specific URL; the global "
            "archive is ~1.35 GB."
        ),
    )

    def __init__(self, path: str | Path | None = None, url: str | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.url = url

    def plan_downloads(self, taxid: int) -> list[DownloadSpec]:
        if self.path is not None:
            return []
        return [
            DownloadSpec(
                url=self.url or GLOBAL_MITAB_URL,
                filename="intact.zip",
                headers={"User-Agent": "Mozilla/5.0"},
                note="Large PSI-MITAB archive (~1.35 GB).",
            )
        ]

    def parse(self, files: Mapping[str, Path], *, taxid: int) -> SourceData:
        if self.path is not None:
            path = self.path
        else:
            candidate = files.get("intact.zip") or (next(iter(files.values())) if files else None)
            if candidate is None:
                raise SourceError("IntAct source needs a local path or a download URL")
            path = candidate
        edges, nodes = parse_intact(path, taxid)
        return SourceData(source=self.metadata.name, edges=edges, nodes=nodes)
