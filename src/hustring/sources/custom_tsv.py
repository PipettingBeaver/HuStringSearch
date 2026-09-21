"""Custom user-supplied edge list (TSV/CSV) as an overlay source."""

from __future__ import annotations

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


def _select(frame: pd.DataFrame, column: int | str) -> pd.Series:
    if isinstance(column, int):
        return frame.iloc[:, column]
    if column not in frame.columns:
        raise SourceError(f"column '{column}' not found; columns are {list(frame.columns)}")
    return frame[column]


@register
class CustomTSVSource(InteractomeSource):
    metadata = SourceMetadata(
        name="custom",
        display_name="Custom edge list",
        namespace="custom",
        version="user",
        supported_taxids=None,
        directed=False,
        default_weight=1.0,
        notes="User-provided overlay; identifiers mapped like any other namespace.",
    )

    def __init__(
        self,
        path: str | Path,
        a_col: int | str = 0,
        b_col: int | str = 1,
        weight_col: int | str | None = None,
        sep: str = "\t",
        header: int | None = 0,
        comment: str = "#",
        namespace: str = "custom",
        default_weight: float = 1.0,
    ) -> None:
        self.path = Path(path)
        self.a_col = a_col
        self.b_col = b_col
        self.weight_col = weight_col
        self.sep = sep
        self.header = header
        self.comment = comment
        self._namespace = namespace
        self.default_weight = default_weight

    @property
    def namespace(self) -> str:
        return self._namespace

    def plan_downloads(self, taxid: int) -> list[DownloadSpec]:
        return []

    def parse(self, files: Mapping[str, Path], *, taxid: int) -> SourceData:
        if not self.path.exists():
            raise SourceError(f"custom edge list not found: {self.path}")
        frame = pd.read_csv(
            self.path,
            sep=self.sep,
            header=self.header,
            comment=self.comment,
            dtype=str,
            skip_blank_lines=True,
        )
        a = _select(frame, self.a_col)
        b = _select(frame, self.b_col)
        if self.weight_col is None:
            weight = pd.Series(self.default_weight, index=frame.index, dtype=float)
        else:
            weight = pd.to_numeric(_select(frame, self.weight_col), errors="coerce").fillna(
                self.default_weight
            )
        edges = pd.DataFrame({"a": a, "b": b, "weight": weight})
        edges = edges.dropna(subset=["a", "b"])
        nodes = make_nodes(pd.DataFrame({"id": pd.unique(pd.concat([a, b]).dropna())}))
        return SourceData(
            source=self.metadata.name, edges=make_edges(edges), nodes=nodes
        )
