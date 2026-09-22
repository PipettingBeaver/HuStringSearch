"""Gene-name enrichment: caching, parsing, and graceful degradation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hustring.errors import MappingError
from hustring.mapping import enrich


class FakeClient:
    """Stands in for BiomartClient, returning a canned frame or raising."""

    def __init__(self, frame: pd.DataFrame | None = None, error: Exception | None = None):
        self.frame = frame
        self.error = error
        self.calls = 0

    def query(self, xml: str) -> pd.DataFrame:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.frame is not None
        return self.frame


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ensembl_gene_id": ["ENSG1", "ENSG2", "ENSG3"],
            "external_gene_name": ["TP53", "", "BRCA1"],
            "description": ["p53 desc", "fallback name", ""],
        }
    )


def test_fetch_uses_gene_name_then_description_fallback(tmp_path: Path) -> None:
    client = FakeClient(_frame())
    names = enrich.fetch_gene_names(9606, tmp_path, client=client)
    assert names["ENSG1"] == "TP53"
    assert names["ENSG2"] == "fallback name"  # empty external_gene_name -> description
    assert names["ENSG3"] == "BRCA1"  # has a gene name, so description is ignored


def test_no_usable_names_raises(tmp_path: Path) -> None:
    """A response with no usable names is treated as an enrichment failure."""
    frame = pd.DataFrame(
        {
            "ensembl_gene_id": ["ENSG1"],
            "external_gene_name": [""],
            "description": [""],
        }
    )
    with pytest.raises(MappingError):
        enrich.fetch_gene_names(9606, tmp_path, client=FakeClient(frame))


def test_result_is_cached_and_reused(tmp_path: Path) -> None:
    client = FakeClient(_frame())
    enrich.fetch_gene_names(9606, tmp_path, client=client)
    second = FakeClient(_frame())
    names = enrich.fetch_gene_names(9606, tmp_path, client=second)
    assert second.calls == 0  # served from cache
    assert names["ENSG1"] == "TP53"


def test_force_bypasses_cache(tmp_path: Path) -> None:
    enrich.fetch_gene_names(9606, tmp_path, client=FakeClient(_frame()))
    second = FakeClient(_frame())
    enrich.fetch_gene_names(9606, tmp_path, client=second, force=True)
    assert second.calls == 1


def test_query_failure_raises_mapping_error(tmp_path: Path) -> None:
    client = FakeClient(error=MappingError("BioMart query failed: down"))
    with pytest.raises(MappingError):
        enrich.fetch_gene_names(9606, tmp_path, client=client)


def test_unknown_taxon_without_dataset_raises(tmp_path: Path) -> None:
    with pytest.raises(MappingError):
        enrich.fetch_gene_names(999999, tmp_path, client=FakeClient(_frame()))


def test_build_continues_when_enrichment_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The graph build must never fail because gene names could not be fetched."""
    from hustring.graph import build as build_module

    def boom(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise MappingError("BioMart down")

    monkeypatch.setattr(build_module, "_enrich_gene_names", build_module._enrich_gene_names)
    import hustring.mapping.enrich as enrich_module

    monkeypatch.setattr(enrich_module, "fetch_gene_names", boom)

    annotations: dict[tuple[str | None, str | None, str | None]] = {}
    with pytest.warns(UserWarning, match="gene-name enrichment skipped"):
        build_module._enrich_gene_names(9606, tmp_path, annotations)
    assert annotations == {}
