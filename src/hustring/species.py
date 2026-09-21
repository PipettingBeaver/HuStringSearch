"""Curated species presets.

Species behavior is driven entirely by an NCBI taxon ID; human is only a
default. Presets exist to make the build window convenient — any taxon ID is
still accepted, in which case the Ensembl division must be supplied explicitly.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class EnsemblDivision(StrEnum):
    """Which Ensembl BioMart (division) hosts a species' identifier mapping."""

    ENSEMBL = "ensembl"
    METAZOA = "ensembl_metazoa"
    FUNGI = "ensembl_fungi"
    PLANTS = "ensembl_plants"
    PROTISTS = "ensembl_protists"
    BACTERIA = "ensembl_bacteria"


class SpeciesPreset(BaseModel):
    """A selectable organism plus how to fetch and map it."""

    model_config = ConfigDict(frozen=True)

    taxid: int
    scientific_name: str
    common_name: str
    ensembl_division: EnsemblDivision
    default_sources: tuple[str, ...]


PRESETS: tuple[SpeciesPreset, ...] = (
    SpeciesPreset(
        taxid=9606,
        scientific_name="Homo sapiens",
        common_name="Human",
        ensembl_division=EnsemblDivision.ENSEMBL,
        default_sources=("huri", "string"),
    ),
    SpeciesPreset(
        taxid=10090,
        scientific_name="Mus musculus",
        common_name="Mouse",
        ensembl_division=EnsemblDivision.ENSEMBL,
        default_sources=("string",),
    ),
    SpeciesPreset(
        taxid=10116,
        scientific_name="Rattus norvegicus",
        common_name="Rat",
        ensembl_division=EnsemblDivision.ENSEMBL,
        default_sources=("string",),
    ),
    SpeciesPreset(
        taxid=7955,
        scientific_name="Danio rerio",
        common_name="Zebrafish",
        ensembl_division=EnsemblDivision.ENSEMBL,
        default_sources=("string",),
    ),
    SpeciesPreset(
        taxid=7227,
        scientific_name="Drosophila melanogaster",
        common_name="Fruit fly",
        ensembl_division=EnsemblDivision.METAZOA,
        default_sources=("string",),
    ),
    SpeciesPreset(
        taxid=6239,
        scientific_name="Caenorhabditis elegans",
        common_name="Nematode",
        ensembl_division=EnsemblDivision.METAZOA,
        default_sources=("string",),
    ),
    SpeciesPreset(
        taxid=559292,
        scientific_name="Saccharomyces cerevisiae S288c",
        common_name="Budding yeast",
        ensembl_division=EnsemblDivision.FUNGI,
        default_sources=("string",),
    ),
    SpeciesPreset(
        taxid=284812,
        scientific_name="Schizosaccharomyces pombe 972h-",
        common_name="Fission yeast",
        ensembl_division=EnsemblDivision.FUNGI,
        default_sources=("string",),
    ),
    SpeciesPreset(
        taxid=3702,
        scientific_name="Arabidopsis thaliana",
        common_name="Thale cress",
        ensembl_division=EnsemblDivision.PLANTS,
        default_sources=("string",),
    ),
    SpeciesPreset(
        taxid=511145,
        scientific_name="Escherichia coli K-12 MG1655",
        common_name="E. coli",
        ensembl_division=EnsemblDivision.BACTERIA,
        default_sources=("string",),
    ),
    SpeciesPreset(
        taxid=224308,
        scientific_name="Bacillus subtilis subsp. subtilis 168",
        common_name="B. subtilis",
        ensembl_division=EnsemblDivision.BACTERIA,
        default_sources=("string",),
    ),
)

PRESETS_BY_TAXID: dict[int, SpeciesPreset] = {p.taxid: p for p in PRESETS}


def lookup_species(taxid: int) -> SpeciesPreset | None:
    """Return the curated preset for ``taxid``, or ``None`` if not curated."""
    return PRESETS_BY_TAXID.get(taxid)


def default_sources_for(taxid: int) -> tuple[str, ...]:
    """Sources to enable by default: curated preset, otherwise STRING only."""
    preset = lookup_species(taxid)
    return preset.default_sources if preset else ("string",)
