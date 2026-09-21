"""Mapping: STRING-derived maps, resolver behavior, and BioMart query/parse."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hustring.errors import MappingError
from hustring.mapping import biomart, resolver, string_map


def test_parse_protein_info(tmp_path: Path) -> None:
    path = tmp_path / "info.tsv"
    path.write_text(
        "#string_protein_id\tpreferred_name\tprotein_size\tannotation\n"
        "9606.ENSP1\tTP53\t393\tp53\n"
    )
    assert string_map.parse_protein_info(path) == {"9606.ENSP1": "TP53"}


def test_parse_aliases_and_build_maps(tmp_path: Path) -> None:
    path = tmp_path / "aliases.tsv"
    path.write_text(
        "9606.ENSP1\tENSG1\tEnsembl_gene\n"
        "9606.ENSP1\tTP53\tEnsembl_HGNC_symbol\n"
        "9606.ENSP1\tP04637\tEnsembl_UniProt\n"
        "9606.ENSP1\t7157\tEnsembl_EntrezGene\n"
        "9606.ENSP2\tOTHER\tEnsembl_HGNC_symbol\n"
    )
    maps = string_map.build_string_maps(string_map.parse_aliases(path))
    assert maps["string"]["9606.ENSP1"] == "ENSG1"
    assert maps["symbol"]["TP53"] == "ENSG1"
    assert maps["uniprot"]["P04637"] == "ENSG1"
    assert maps["entrez"]["7157"] == "ENSG1"
    assert "OTHER" not in maps["symbol"]


def test_canonicalize_strict_and_lenient() -> None:
    res = resolver.IdentifierResolver.from_maps({"string": {"P1": "G1"}})
    edges = pd.DataFrame({"a": ["P1", "PX"], "b": ["P2", "P3"], "weight": [1.0, 2.0]})

    strict, count = res.canonicalize(edges, "string", strict=True)
    assert strict.empty
    assert count == 2

    lenient, count2 = res.canonicalize(edges, "string", strict=False)
    assert set(lenient["a"]) == {"G1", "PX"}
    assert count2 == 2


def test_identity_namespace_needs_no_map() -> None:
    res = resolver.IdentifierResolver.from_maps({})
    edges = pd.DataFrame({"a": ["G1"], "b": ["G2"], "weight": [1.0]})
    out, count = res.canonicalize(edges, "ensembl_gene")
    assert out.iloc[0]["a"] == "G1"
    assert count == 0


def test_build_query_contains_dataset_and_attributes() -> None:
    xml = biomart.build_query(
        "hsapiens_gene_ensembl", ["ensembl_peptide_id", "ensembl_gene_id"]
    )
    assert '<Dataset name="hsapiens_gene_ensembl"' in xml
    assert xml.count("<Attribute") == 2
    assert "<Filter" not in xml


def test_parse_biomart_tsv_ok_and_errors() -> None:
    frame = biomart.parse_biomart_tsv("A\tB\n1\t2\n")
    assert list(frame.columns) == ["A", "B"]
    with pytest.raises(MappingError):
        biomart.parse_biomart_tsv("Query ERROR: nope")
    with pytest.raises(MappingError):
        biomart.parse_biomart_tsv("")
