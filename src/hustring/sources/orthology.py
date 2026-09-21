"""Cross-species orthology bridge via STRING COG mappings.

Verified format: tab-separated, header
``#protein  start_position  end_position  orthologous_group  protein_annotation``
where ``protein`` is ``<taxid>.<protein id>``. Proteins sharing an orthologous
group are connected; pairs within a group are capped to avoid O(n^2) blow-ups.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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

COG_URL = "https://stringdb-downloads.org/download/COG.mappings.v12.0.txt.gz"
COG_FILENAME = "COG.mappings.v12.0.txt.gz"


def _taxid_of(protein_id: str) -> int | None:
    prefix, _, _ = protein_id.partition(".")
    return int(prefix) if prefix.isdigit() else None


def parse_cog_mappings(
    path: Path,
    taxa: Sequence[int],
    *,
    include_within_species: bool = False,
    max_group_size: int = 50,
    default_weight: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Emit orthology edges between proteins sharing a COG across ``taxa``."""
    wanted = {int(t) for t in taxa}
    frame = pd.read_csv(
        path,
        sep="\t",
        dtype=str,
        usecols=["#protein", "orthologous_group"],
        compression="infer",
        low_memory=False,
    )
    frame = frame.rename(columns={"#protein": "protein"})
    frame["taxid"] = frame["protein"].map(_taxid_of)
    frame = frame[frame["taxid"].isin(wanted)].dropna(subset=["taxid"])

    pairs_a: list[str] = []
    pairs_b: list[str] = []
    for _, group in frame.groupby("orthologous_group", sort=False):
        members = group["protein"].tolist()
        member_taxa = group["taxid"].tolist()
        if len(members) > max_group_size:
            members = members[:max_group_size]
            member_taxa = member_taxa[:max_group_size]
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                if include_within_species or member_taxa[i] != member_taxa[j]:
                    pairs_a.append(members[i])
                    pairs_b.append(members[j])

    edges = pd.DataFrame(
        {"a": pairs_a, "b": pairs_b, "weight": float(default_weight)}
    )
    nodes = make_nodes(
        pd.DataFrame({"id": pd.unique(pd.Series(pairs_a + pairs_b, dtype="object"))})
    )
    return make_edges(edges), nodes


@register
class OrthologyBridge(InteractomeSource):
    metadata = SourceMetadata(
        name="orthology",
        display_name="STRING COG orthology bridge",
        namespace="string",
        version="12.0",
        supported_taxids=None,
        directed=False,
        default_weight=1.0,
        citation="STRING COG mappings",
        homepage="https://string-db.org",
        notes=(
            "Adds cross-species edges between proteins in the same COG. The COG "
            "mappings file is ~755 MB and is parsed by streaming/filtering."
        ),
    )

    def __init__(
        self,
        taxa: Sequence[int] | None = None,
        include_within_species: bool = False,
        max_group_size: int = 50,
        default_weight: float = 1.0,
    ) -> None:
        self.taxa = [int(t) for t in taxa] if taxa is not None else None
        self.include_within_species = include_within_species
        self.max_group_size = max_group_size
        self.default_weight = default_weight

    def plan_downloads(self, taxid: int) -> list[DownloadSpec]:
        return [
            DownloadSpec(
                url=COG_URL,
                filename=COG_FILENAME,
                note="Global COG mappings (~755 MB).",
            )
        ]

    def parse(self, files: Mapping[str, Path], *, taxid: int) -> SourceData:
        path = self._single(files, COG_FILENAME)
        taxa = self.taxa if self.taxa is not None else [taxid]
        edges, nodes = parse_cog_mappings(
            path,
            taxa,
            include_within_species=self.include_within_species,
            max_group_size=self.max_group_size,
            default_weight=self.default_weight,
        )
        return SourceData(source=self.metadata.name, edges=edges, nodes=nodes)
