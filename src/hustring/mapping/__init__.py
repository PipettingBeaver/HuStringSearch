"""Identifier harmonization: canonical Ensembl Gene IDs."""

from __future__ import annotations

from .biomart import BiomartClient, build_query, parse_biomart_tsv
from .enrich import fetch_gene_names
from .ensembl_rest import EnsemblRestClient
from .resolver import CANONICAL_NAMESPACE, IdentifierResolver
from .string_map import build_string_maps, parse_aliases, parse_protein_info

__all__ = [
    "CANONICAL_NAMESPACE",
    "BiomartClient",
    "EnsemblRestClient",
    "IdentifierResolver",
    "build_query",
    "build_string_maps",
    "fetch_gene_names",
    "parse_aliases",
    "parse_biomart_tsv",
    "parse_protein_info",
]
