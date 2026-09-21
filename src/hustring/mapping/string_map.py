"""Build canonical ID maps from STRING's own info/alias files.

STRING's alias file carries ``Ensembl_gene`` / ``Ensembl_HGNC_ensembl_gene_id``
entries that resolve a STRING protein ID straight to an Ensembl Gene ID, so the
full STRING -> canonical mapping needs no external service. This is the robust
default; BioMart is an optional augmentation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

GENE_SOURCES = frozenset({"Ensembl_gene", "Ensembl_HGNC_ensembl_gene_id"})
SYMBOL_SOURCES = frozenset({"Ensembl_HGNC_symbol"})
UNIPROT_SOURCES = frozenset(
    {"Ensembl_UniProt", "UniProt_AC", "Ensembl_HGNC_uniprot_ids"}
)
ENTREZ_SOURCES = frozenset({"Ensembl_EntrezGene"})
ALL_SOURCES = GENE_SOURCES | SYMBOL_SOURCES | UNIPROT_SOURCES | ENTREZ_SOURCES


def parse_protein_info(path: Path) -> dict[str, str]:
    """Parse ``<taxid>.protein.info`` into {protein_id: preferred symbol}."""
    frame = pd.read_csv(path, sep="\t", dtype=str)
    frame = frame.rename(columns={"#string_protein_id": "protein", "preferred_name": "symbol"})
    frame = frame.dropna(subset=["protein", "symbol"])
    return dict(zip(frame["protein"], frame["symbol"], strict=False))


def parse_aliases(path: Path, sources: frozenset[str] = ALL_SOURCES) -> pd.DataFrame:
    """Parse ``<taxid>.protein.aliases`` into a (protein, alias, source) frame."""
    frame = pd.read_csv(
        path,
        sep="\t",
        header=None,
        names=["protein", "alias", "source"],
        dtype=str,
        usecols=[0, 1, 2],
    )
    frame = frame.dropna(subset=["protein", "alias", "source"])
    frame = frame[~frame["protein"].str.startswith("#")]
    return frame[frame["source"].isin(sources)].reset_index(drop=True)


def build_string_maps(
    aliases: pd.DataFrame,
    protein_symbol: dict[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    """Turn a filtered alias frame into namespace -> {native id: ENSG} maps."""
    gene_rows = aliases[aliases["source"].isin(GENE_SOURCES)]
    protein_to_gene = dict(zip(gene_rows["protein"], gene_rows["alias"], strict=False))

    def forward(rows: pd.DataFrame) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for protein, alias in zip(rows["protein"], rows["alias"], strict=False):
            gene = protein_to_gene.get(protein)
            if gene is not None and alias not in resolved:
                resolved[alias] = gene
        return resolved

    symbol_map = forward(aliases[aliases["source"].isin(SYMBOL_SOURCES)])
    if protein_symbol:
        for protein, symbol in protein_symbol.items():
            gene = protein_to_gene.get(protein)
            if gene is not None and symbol not in symbol_map:
                symbol_map[symbol] = gene

    return {
        "string": dict(protein_to_gene),
        "ensembl_protein": dict(protein_to_gene),
        "symbol": symbol_map,
        "uniprot": forward(aliases[aliases["source"].isin(UNIPROT_SOURCES)]),
        "entrez": forward(aliases[aliases["source"].isin(ENTREZ_SOURCES)]),
    }
