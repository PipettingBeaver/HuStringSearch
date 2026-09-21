"""STRING source.

Formats verified against STRING v12.0 human downloads:
- links: space-separated, header ``protein1 protein2 combined_score`` (0-1000)
- info: tab-separated, header ``#string_protein_id preferred_name protein_size annotation``
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
    make_nodes,
)
from .registry import register

BASE_URL = "https://stringdb-downloads.org/download"
SCORE_MAX = 1000


def links_filename(taxid: int, version: str) -> str:
    return f"{taxid}.protein.links.v{version}.txt.gz"


def info_filename(taxid: int, version: str) -> str:
    return f"{taxid}.protein.info.v{version}.txt.gz"


def parse_links(path: Path, *, min_score: int | None = None) -> pd.DataFrame:
    """Parse STRING protein links into a (a, b, score) frame."""
    frame = pd.read_csv(
        path,
        sep=r"\s+",
        dtype={"protein1": "string", "protein2": "string", "combined_score": "int64"},
    )
    frame = frame.rename(columns={"protein1": "a", "protein2": "b"})
    if min_score is not None:
        frame = frame[frame["combined_score"] >= min_score]
    edges = pd.DataFrame(
        {
            "a": frame["a"],
            "b": frame["b"],
            "weight": frame["combined_score"].astype(float) / SCORE_MAX,
        }
    )
    return make_edges(edges)


def parse_info(path: Path) -> pd.DataFrame:
    """Parse STRING protein info into the node schema."""
    frame = pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        keep_default_na=False,
        na_values=[],
    )
    frame = frame.rename(
        columns={
            "#string_protein_id": "id",
            "preferred_name": "symbol",
            "annotation": "description",
        }
    )
    return make_nodes(frame)


@register
class StringSource(InteractomeSource):
    metadata = SourceMetadata(
        name="string",
        display_name="STRING",
        namespace="string",
        version="12.0",
        supported_taxids=None,
        directed=False,
        default_weight=1.0,
        citation="Szklarczyk et al., Nucleic Acids Research (2023)",
        homepage="https://string-db.org",
        notes="Combined confidence score, normalized to 0-1.",
    )

    def __init__(self, version: str = "12.0", min_score: int | None = None) -> None:
        self.version = version
        self.min_score = min_score

    def plan_downloads(self, taxid: int) -> list[DownloadSpec]:
        return [
            DownloadSpec(
                url=f"{BASE_URL}/protein.links.v{self.version}/"
                f"{links_filename(taxid, self.version)}",
                filename=links_filename(taxid, self.version),
                note="Scored links for the organism.",
            ),
            DownloadSpec(
                url=f"{BASE_URL}/protein.info.v{self.version}/"
                f"{info_filename(taxid, self.version)}",
                filename=info_filename(taxid, self.version),
                note="Protein display names and descriptions.",
            ),
        ]

    def parse(self, files: Mapping[str, Path], *, taxid: int) -> SourceData:
        links = self._single(files, links_filename(taxid, self.version))
        info = self._single(files, info_filename(taxid, self.version))
        edges = parse_links(links, min_score=self.min_score)
        nodes = parse_info(info)
        return SourceData(source=self.metadata.name, edges=edges, nodes=nodes)
