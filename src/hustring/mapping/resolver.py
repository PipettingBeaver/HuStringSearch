"""Resolve source-native identifiers to the canonical Ensembl Gene ID space."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

CANONICAL_NAMESPACE = "ensembl_gene"
STRING_MAP_BASE = "https://stringdb-downloads.org/download"


@dataclass(slots=True)
class IdentifierResolver:
    """Maps per-namespace native identifiers to canonical Ensembl Gene IDs."""

    maps: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def from_maps(cls, maps: dict[str, dict[str, str]]) -> IdentifierResolver:
        return cls(maps={key: dict(value) for key, value in maps.items()})

    @classmethod
    def from_string(
        cls,
        taxid: int,
        cache_dir: Path,
        *,
        version: str = "12.0",
    ) -> IdentifierResolver:
        """Build maps from STRING's own info + aliases files (no BioMart needed)."""
        from ..sources.base import DownloadSpec
        from ..sources.download import download_files
        from .string_map import build_string_maps, parse_aliases, parse_protein_info

        info_name = f"{taxid}.protein.info.v{version}.txt.gz"
        alias_name = f"{taxid}.protein.aliases.v{version}.txt.gz"
        specs = [
            DownloadSpec(
                url=f"{STRING_MAP_BASE}/protein.info.v{version}/{info_name}",
                filename=info_name,
            ),
            DownloadSpec(
                url=f"{STRING_MAP_BASE}/protein.aliases.v{version}/{alias_name}",
                filename=alias_name,
            ),
        ]
        files = download_files(specs, Path(cache_dir))
        protein_symbol = parse_protein_info(files[info_name])
        aliases = parse_aliases(files[alias_name])
        return cls(build_string_maps(aliases, protein_symbol))

    def with_extra(self, namespace: str, table: dict[str, str]) -> IdentifierResolver:
        """Return a resolver with an additional/merged namespace table."""
        merged = {key: dict(value) for key, value in self.maps.items()}
        merged.setdefault(namespace, {}).update(table)
        return IdentifierResolver(merged)

    def resolve(self, native: str, namespace: str) -> str | None:
        if namespace == CANONICAL_NAMESPACE:
            return native
        return self.maps.get(namespace, {}).get(native)

    def canonicalize(
        self,
        edges: pd.DataFrame,
        namespace: str,
        *,
        strict: bool = True,
    ) -> tuple[pd.DataFrame, int]:
        """Return edges with canonical ``a``/``b`` plus the count left unmapped."""
        if namespace == CANONICAL_NAMESPACE:
            out = edges.copy()
            out["a"] = out["a"].astype(str)
            out["b"] = out["b"].astype(str)
            return out, 0

        table = self.maps.get(namespace)
        if not table:
            return edges.iloc[0:0].copy(), len(edges)

        mapped_a = edges["a"].map(table)
        mapped_b = edges["b"].map(table)
        unmapped = mapped_a.isna() | mapped_b.isna()
        count = int(unmapped.sum())
        if strict:
            keep = ~unmapped
            out = edges.loc[keep].copy()
            out["a"] = mapped_a[keep].astype(str)
            out["b"] = mapped_b[keep].astype(str)
        else:
            out = edges.copy()
            out["a"] = mapped_a.fillna(edges["a"]).astype(str)
            out["b"] = mapped_b.fillna(edges["b"]).astype(str)
        return out, count

    def canonical_ids(self, native: pd.Series, namespace: str) -> pd.Series:
        """Vectorized mapping of a native ID series to canonical IDs."""
        if namespace == CANONICAL_NAMESPACE:
            return native.astype(str)
        return native.map(self.maps.get(namespace, {}))
