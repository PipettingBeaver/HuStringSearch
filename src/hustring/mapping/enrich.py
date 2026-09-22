"""Build-time enrichment of node annotations from Ensembl BioMart.

Gene names are decorative: they describe a node but do not affect the graph or the
walk. Per ADR D10a they are fetched once, batched, and cached at build time, and any
failure degrades gracefully (the caller keeps whatever it already had). Nothing here
runs in the request path.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import MappingError
from ..species import EnsemblDivision, lookup_species
from .biomart import DEFAULT_MART, BiomartClient

GENE_NAME_ATTR = "external_gene_name"
FALLBACK_ATTR = "description"
DATASET_FOR_DIVISION: dict[EnsemblDivision, str] = {
    EnsemblDivision.ENSEMBL: "hsapiens_gene_ensembl",
    EnsemblDivision.METAZOA: "dmelanogaster_gene_ensembl",
    EnsemblDivision.FUNGI: "scerevisiae_gene_ensembl",
    EnsemblDivision.PLANTS: "athaliana_gene_ensembl",
    EnsemblDivision.PROTISTS: "pfa1_gene_ensembl",
    EnsemblDivision.BACTERIA: "escherichia_coli_k_12_mg1655_gene_ensembl",
}


def cache_path(cache_dir: Path, taxid: int) -> Path:
    return Path(cache_dir) / "mapping" / f"{taxid}.gene_names.json"


def load_cached(cache_dir: Path, taxid: int) -> dict[str, str]:
    """Return cached gene names, or an empty mapping if none are cached."""
    path = cache_path(cache_dir, taxid)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _save_cache(mapping: dict[str, str], cache_dir: Path, taxid: int) -> None:
    path = cache_path(cache_dir, taxid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=0, sort_keys=True))


def dataset_for(taxid: int) -> str | None:
    """Ensembl dataset name for a curated species, or None if unknown."""
    preset = lookup_species(taxid)
    if preset is None:
        return None
    return DATASET_FOR_DIVISION.get(preset.ensembl_division)


def fetch_gene_names(
    taxid: int,
    cache_dir: Path,
    *,
    client: BiomartClient | None = None,
    dataset: str | None = None,
    force: bool = False,
) -> dict[str, str]:
    """Return {ensembl_gene_id: gene_name} for the organism, cached on disk.

    Raises :class:`MappingError` when the query fails; callers should treat gene
    names as optional and continue without them.
    """
    if not force:
        cached = load_cached(cache_dir, taxid)
        if cached:
            return cached

    resolved_dataset = dataset or dataset_for(taxid)
    if resolved_dataset is None:
        raise MappingError(
            f"no Ensembl dataset known for taxon {taxid}; pass an explicit dataset"
        )

    if client is None:
        preset = lookup_species(taxid)
        division = preset.ensembl_division if preset else EnsemblDivision.ENSEMBL
        client = BiomartClient.for_division(division)

    xml = _names_query(resolved_dataset)
    frame = client.query(xml)
    if "ensembl_gene_id" not in frame.columns:
        raise MappingError(f"unexpected BioMart columns: {list(frame.columns)}")

    mapping: dict[str, str] = {}
    for row in frame.to_dict("records"):
        gene_id = row.get("ensembl_gene_id")
        if not isinstance(gene_id, str) or not gene_id:
            continue
        name = row.get(GENE_NAME_ATTR)
        if not isinstance(name, str) or not name.strip():
            name = row.get(FALLBACK_ATTR)
        if isinstance(name, str) and name.strip():
            mapping[gene_id] = name.strip()
    if not mapping:
        raise MappingError("BioMart returned no usable gene names")
    _save_cache(mapping, cache_dir, taxid)
    return mapping


def _names_query(dataset: str) -> str:
    from .biomart import build_query

    return build_query(
        dataset,
        ["ensembl_gene_id", GENE_NAME_ATTR, FALLBACK_ATTR],
        mart=DEFAULT_MART,
    )
