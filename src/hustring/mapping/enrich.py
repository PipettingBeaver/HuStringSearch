"""Build-time enrichment of node annotations from Ensembl.

Gene names are decorative: they describe a node but do not affect the graph or the
walk. Per ADR D10a they are fetched once, batched, and cached at build time, and any
failure degrades gracefully (the caller keeps whatever it already had). Nothing here
runs in the request path.

Sources are tried in order: the Ensembl **REST API** first (separate infrastructure
from BioMart, often up when BioMart is not), then **BioMart** as a fallback.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from ..errors import MappingError
from ..species import EnsemblDivision, lookup_species
from .biomart import DEFAULT_MART, BiomartClient
from .ensembl_rest import EnsemblRestClient

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
    gene_ids: Iterable[str] | None = None,
    rest_client: EnsemblRestClient | None = None,
    biomart_client: BiomartClient | None = None,
    dataset: str | None = None,
    force: bool = False,
) -> dict[str, str]:
    """Return {ensembl_gene_id: gene_name} for the organism, cached on disk.

    ``gene_ids`` restricts the query to a known node set (recommended, and required
    for REST bulk lookup). Without it, BioMart is used to fetch names for the whole
    organism. Cached names are kept and merged with a fetch for the IDs that are
    not cached yet, so a growing node set never refetches known names. Raises
    :class:`MappingError` if every source fails and nothing is cached; callers
    should treat gene names as optional and continue.
    """
    cached = {} if force else load_cached(cache_dir, taxid)
    ids = list(gene_ids) if gene_ids is not None else None

    if ids is None:
        if cached:
            return cached
        missing: list[str] | None = None
    else:
        missing = [gene_id for gene_id in ids if gene_id not in cached]
        if not missing:
            return cached

    errors: list[str] = []

    if missing:
        client = rest_client or EnsemblRestClient()
        try:
            fetched = client.gene_names(missing)
            if fetched:
                merged = {**cached, **fetched}
                _save_cache(merged, cache_dir, taxid)
                return merged
            errors.append("Ensembl REST returned no names")
        except MappingError as exc:
            errors.append(f"Ensembl REST: {exc}")

    try:
        mapping = _fetch_from_biomart(taxid, cache_dir, dataset, biomart_client)
        if mapping:
            merged = {**cached, **mapping}
            _save_cache(merged, cache_dir, taxid)
            return merged
        errors.append("BioMart returned no names")
    except MappingError as exc:
        errors.append(f"BioMart: {exc}")

    if cached:
        return cached
    raise MappingError("; ".join(errors) or "no gene-name source available")


def _fetch_from_biomart(
    taxid: int,
    cache_dir: Path,
    dataset: str | None,
    client: BiomartClient | None,
) -> dict[str, str]:
    resolved_dataset = dataset or dataset_for(taxid)
    if resolved_dataset is None:
        raise MappingError(f"no Ensembl dataset known for taxon {taxid}")

    if client is None:
        preset = lookup_species(taxid)
        division = preset.ensembl_division if preset else EnsemblDivision.ENSEMBL
        client = BiomartClient.for_division(division)

    from .biomart import build_query

    xml = build_query(
        resolved_dataset,
        ["ensembl_gene_id", GENE_NAME_ATTR, FALLBACK_ATTR],
        mart=DEFAULT_MART,
    )
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
    return mapping
