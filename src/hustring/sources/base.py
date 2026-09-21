"""Interactome source interface and normalized data containers.

A source knows how to (a) declare which organisms it supports, (b) plan the
files it needs, (c) parse raw files into a normalized edge/node schema. The
canonical identifier space is applied later by the mapping layer, so sources
emit IDs in their own namespace.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import pandas as pd

from ..errors import SourceError

EDGE_COLUMNS: tuple[str, ...] = ("a", "b", "weight")
NODE_COLUMNS: tuple[str, ...] = ("id", "symbol", "description")


@dataclass(frozen=True, slots=True)
class DownloadSpec:
    """A single downloadable artifact."""

    url: str
    filename: str
    required: bool = True
    headers: Mapping[str, str] = field(default_factory=dict)
    expected_bytes: int | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    """Static description of a source, used by the registry and the UI."""

    name: str
    display_name: str
    namespace: str
    version: str
    supported_taxids: frozenset[int] | None = None
    directed: bool = False
    default_weight: float = 1.0
    citation: str = ""
    homepage: str = ""
    notes: str = ""


def make_edges(data: Mapping[str, object] | pd.DataFrame) -> pd.DataFrame:
    """Normalize arbitrary edge data into the canonical edge schema."""
    frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    missing = [c for c in EDGE_COLUMNS if c not in frame.columns]
    if missing:
        raise SourceError(f"edge data missing columns: {missing}")
    frame = frame.loc[:, list(EDGE_COLUMNS)].copy()
    frame["a"] = frame["a"].astype(str)
    frame["b"] = frame["b"].astype(str)
    frame["weight"] = frame["weight"].astype(float)
    return frame.reset_index(drop=True)


def make_nodes(data: Mapping[str, object] | pd.DataFrame | None = None) -> pd.DataFrame:
    """Normalize arbitrary node data into the canonical node schema."""
    if data is None or (isinstance(data, pd.DataFrame) and data.empty):
        return pd.DataFrame({column: pd.Series(dtype="object") for column in NODE_COLUMNS})
    frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    for column in NODE_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame.loc[:, list(NODE_COLUMNS)].copy()
    frame["id"] = frame["id"].astype(str)
    return frame.reset_index(drop=True)


@dataclass(slots=True)
class SourceData:
    """Normalized output of a source: edges plus optional node annotations."""

    source: str
    edges: pd.DataFrame
    nodes: pd.DataFrame = field(default_factory=make_nodes)
    directed: bool = False

    def __post_init__(self) -> None:
        missing = [c for c in EDGE_COLUMNS if c not in self.edges.columns]
        if missing:
            raise SourceError(f"SourceData edges missing columns: {missing}")
        if not self.nodes.empty:
            node_missing = [c for c in NODE_COLUMNS if c not in self.nodes.columns]
            if node_missing:
                raise SourceError(f"SourceData nodes missing columns: {node_missing}")

    @property
    def n_edges(self) -> int:
        return len(self.edges)

    @property
    def n_nodes(self) -> int:
        if self.nodes.empty:
            return int(pd.unique(pd.concat([self.edges["a"], self.edges["b"]])).size)
        return int(self.nodes["id"].nunique())


class InteractomeSource(ABC):
    """Base class for pluggable interactome sources."""

    metadata: ClassVar[SourceMetadata]

    @property
    def namespace(self) -> str:
        """Identifier namespace this source's edges use."""
        return self.metadata.namespace

    def supports(self, taxid: int) -> bool:
        """Whether this source can provide data for ``taxid``."""
        supported = self.metadata.supported_taxids
        return supported is None or taxid in supported

    @abstractmethod
    def plan_downloads(self, taxid: int) -> list[DownloadSpec]:
        """Files required to build for ``taxid`` (may be empty for local sources)."""

    @abstractmethod
    def parse(self, files: Mapping[str, Path], *, taxid: int) -> SourceData:
        """Parse already-downloaded files into normalized ``SourceData``."""

    def fetch(
        self,
        taxid: int,
        cache_dir: Path,
        *,
        force: bool = False,
    ) -> SourceData:
        """Download (if needed) and parse the source for ``taxid``."""
        from .download import download_files

        if not self.supports(taxid):
            raise SourceError(
                f"source '{self.metadata.name}' does not support taxon {taxid}"
            )
        specs = self.plan_downloads(taxid)
        paths = download_files(specs, Path(cache_dir) / self.metadata.name, force=force)
        return self.parse(paths, taxid=taxid)

    @staticmethod
    def _single(files: Mapping[str, Path], filename: str) -> Path:
        """Return a named file, or the only file when the name is not exact."""
        if filename in files:
            return files[filename]
        if len(files) == 1:
            return next(iter(files.values()))
        raise SourceError(f"expected file '{filename}' not found in {list(files)}")
