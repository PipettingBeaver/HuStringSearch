"""HuRI source (Human Reference Interactome).

Verified format: tab-separated, no header, two Ensembl Gene IDs per line.
HuRI is human-only and already keyed by Ensembl Gene ID, so it needs no mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from .base import (
    DownloadSpec,
    InteractomeSource,
    SourceData,
    SourceMetadata,
    make_edges,
)
from .registry import register

HURI_URL = "https://interactome-atlas.org/data/HuRI.tsv"
HURI_FILENAME = "HuRI.tsv"


def parse_huri(path: Path) -> pd.DataFrame:
    """Parse headerless HuRI ENSG pairs into the edge schema."""
    frame = pd.read_csv(
        path,
        sep="\t",
        header=None,
        names=["a", "b"],
        dtype=str,
        comment="#",
    )
    frame["weight"] = 1.0
    return make_edges(frame)


@register
class HuriSource(InteractomeSource):
    metadata = SourceMetadata(
        name="huri",
        display_name="HuRI",
        namespace="ensembl_gene",
        version="HI-III-20",
        supported_taxids=frozenset({9606}),
        directed=False,
        default_weight=1.0,
        citation="Luck et al., Nature (2020)",
        homepage="https://interactome-atlas.org",
        notes="Binary experimental map; already in Ensembl Gene IDs.",
    )

    def plan_downloads(self, taxid: int) -> list[DownloadSpec]:
        return [
            DownloadSpec(
                url=HURI_URL,
                filename=HURI_FILENAME,
                headers={"User-Agent": "Mozilla/5.0"},
                note="HuRI binary interaction list.",
            )
        ]

    def parse(self, files: Mapping[str, Path], *, taxid: int) -> SourceData:
        path = self._single(files, HURI_FILENAME)
        return SourceData(source=self.metadata.name, edges=parse_huri(path))
