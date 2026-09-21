"""Ensembl BioMart client.

BioMart is optional: STRING's alias files already map to Ensembl Gene IDs. This
client is used to fill gaps and for identifiers STRING does not cover. The stable
Ensembl host 308-redirects to the current release archive, so requests follow
redirects automatically.

Only the query builder and TSV parser touch no network, so they are unit-tested.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from ..errors import MappingError
from ..species import EnsemblDivision

DIVISION_HOSTS: dict[EnsemblDivision, str] = {
    EnsemblDivision.ENSEMBL: "https://www.ensembl.org/biomart/martservice",
    EnsemblDivision.METAZOA: "https://metazoa.ensembl.org/biomart/martservice",
    EnsemblDivision.FUNGI: "https://fungi.ensembl.org/biomart/martservice",
    EnsemblDivision.PLANTS: "https://plants.ensembl.org/biomart/martservice",
    EnsemblDivision.PROTISTS: "https://protists.ensembl.org/biomart/martservice",
    EnsemblDivision.BACTERIA: "https://bacteria.ensembl.org/biomart/martservice",
}
DEFAULT_MART = "ENSEMBL_MART_ENSEMBL"


def build_query(
    dataset: str,
    attributes: list[str],
    filters: dict[str, str] | None = None,
    *,
    mart: str = DEFAULT_MART,
    header: bool = True,
    formatter: str = "TSV",
) -> str:
    """Build a BioMart XML query string."""
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!DOCTYPE Query>",
        f'<Query virtualSchemaName="{mart}" formatter="{formatter}" header="{int(header)}" '
        'uniqueRows="1" count="" datasetConfigVersion="0.6">',
        f'  <Dataset name="{dataset}" interface="default">',
    ]
    for name, value in (filters or {}).items():
        parts.append(f'    <Filter name="{name}" value="{value}"/>')
    parts.extend(f'    <Attribute name="{name}"/>' for name in attributes)
    parts.append("  </Dataset>")
    parts.append("</Query>")
    return "\n".join(parts)


def parse_biomart_tsv(text: str) -> pd.DataFrame:
    """Parse a BioMart TSV response, raising on a query error."""
    stripped = text.strip()
    if not stripped:
        raise MappingError("empty BioMart response")
    if stripped.startswith("Query ERROR") or "Service unavailable" in stripped[:400]:
        raise MappingError(f"BioMart query failed: {stripped[:200]}")
    return pd.read_csv(StringIO(stripped), sep="\t", dtype=str)


class BiomartClient:
    """Thin BioMart query client with redirect following."""

    def __init__(self, base_url: str, *, timeout: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def for_division(
        cls, division: EnsemblDivision, *, timeout: float = 180.0
    ) -> BiomartClient:
        host = DIVISION_HOSTS.get(division)
        if host is None:
            raise MappingError(f"no BioMart host known for division '{division}'")
        return cls(host, timeout=timeout)

    def query(self, xml: str) -> pd.DataFrame:
        """Run a BioMart XML query and parse the TSV result."""
        try:
            response = requests.get(
                self.base_url,
                params={"query": xml},
                timeout=self.timeout,
                allow_redirects=True,
                headers={"User-Agent": "HuStringSearch/0.0.1"},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise MappingError(f"BioMart request failed: {exc}") from exc
        return parse_biomart_tsv(response.text)

    def gene_id_map(
        self,
        dataset: str,
        id_attribute: str,
        *,
        gene_attribute: str = "ensembl_gene_id",
        mart: str = DEFAULT_MART,
    ) -> dict[str, str]:
        """Map a dataset identifier attribute to Ensembl Gene IDs."""
        xml = build_query(dataset, [id_attribute, gene_attribute], mart=mart)
        frame = self.query(xml)
        if id_attribute not in frame.columns or gene_attribute not in frame.columns:
            raise MappingError(
                f"unexpected BioMart columns {list(frame.columns)}; "
                f"expected {id_attribute}, {gene_attribute}"
            )
        frame = frame.dropna(subset=[id_attribute, gene_attribute])
        return dict(zip(frame[id_attribute], frame[gene_attribute], strict=False))

    def cache_to_parquet(self, frame: pd.DataFrame, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        return path
