"""BioGRID source, using the BioGRID TAB 3.0 format.

TAB 3.0 has a header row, so columns are addressed by name. Organism ID columns
are NCBI taxonomy IDs, which makes taxon filtering straightforward. Downloads are
zip archives containing one tab-separated file; pandas reads them directly.
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

RELEASE_BASE = "https://downloads.thebiogrid.org/Download/BioGRID/Latest-Release"
SYMBOL_A = "Official Symbol Interactor A"
SYMBOL_B = "Official Symbol Interactor B"
TAXID_A = "Organism ID Interactor A"
TAXID_B = "Organism ID Interactor B"
USECOLS = [SYMBOL_A, SYMBOL_B, TAXID_A, TAXID_B]


def parse_biogrid(path: Path, taxid: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Filter BioGRID TAB 3.0 to one organism and return (edges, nodes)."""
    frame = pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        usecols=USECOLS,
        compression="infer",
        low_memory=False,
    )
    frame = frame[(frame[TAXID_A] == str(taxid)) & (frame[TAXID_B] == str(taxid))]
    frame = frame.replace("-", pd.NA).dropna(subset=[SYMBOL_A, SYMBOL_B])
    edges = pd.DataFrame({"a": frame[SYMBOL_A], "b": frame[SYMBOL_B], "weight": 1.0})
    symbols = pd.unique(pd.concat([frame[SYMBOL_A], frame[SYMBOL_B]]))
    nodes = make_nodes(pd.DataFrame({"id": symbols}))
    return make_edges(edges), nodes


@register
class BiogridSource(InteractomeSource):
    metadata = SourceMetadata(
        name="biogrid",
        display_name="BioGRID",
        namespace="symbol",
        version="LATEST",
        supported_taxids=None,
        directed=False,
        default_weight=1.0,
        citation="Oughtred et al., Protein Science (2021)",
        homepage="https://thebiogrid.org",
        notes="Downloads the all-species TAB 3.0 archive (~170 MB) and filters by taxon.",
    )

    def __init__(self, release: str = "LATEST") -> None:
        self.release = release

    def plan_downloads(self, taxid: int) -> list[DownloadSpec]:
        filename = f"BIOGRID-ALL-{self.release}.tab3.zip"
        return [
            DownloadSpec(
                url=f"{RELEASE_BASE}/{filename}",
                filename=filename,
                headers={"User-Agent": "Mozilla/5.0"},
                note="All-species TAB 3.0 archive; large.",
            )
        ]

    def parse(self, files: Mapping[str, Path], *, taxid: int) -> SourceData:
        path = self._single(files, f"BIOGRID-ALL-{self.release}.tab3.zip")
        edges, nodes = parse_biogrid(path, taxid)
        return SourceData(source=self.metadata.name, edges=edges, nodes=nodes)
