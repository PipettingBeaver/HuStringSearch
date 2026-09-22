"""Gene-name enrichment: REST primary, BioMart fallback, caching, degradation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from hustring.errors import MappingError
from hustring.mapping import enrich


class FakeRest:
    def __init__(
        self,
        mapping: dict[str, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.mapping = mapping or {}
        self.error = error
        self.calls = 0

    def gene_names(self, gene_ids: list[str]) -> dict[str, str]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return {gid: self.mapping[gid] for gid in gene_ids if gid in self.mapping}


class FakeBiomart:
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


def _biomart_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ensembl_gene_id": ["ENSG1", "ENSG2", "ENSG3"],
            "external_gene_name": ["TP53", "", "BRCA1"],
            "description": ["p53 desc", "fallback name", ""],
        }
    )


def test_rest_is_used_first(tmp_path: Path) -> None:
    rest = FakeRest({"ENSG1": "TP53"})
    biomart = FakeBiomart(_biomart_frame())
    names = enrich.fetch_gene_names(
        9606, tmp_path, gene_ids=["ENSG1"], rest_client=rest, biomart_client=biomart
    )
    assert names == {"ENSG1": "TP53"}
    assert rest.calls == 1
    assert biomart.calls == 0  # never needed


def test_falls_back_to_biomart_when_rest_fails(tmp_path: Path) -> None:
    rest = FakeRest(error=MappingError("REST down"))
    biomart = FakeBiomart(_biomart_frame())
    names = enrich.fetch_gene_names(
        9606, tmp_path, gene_ids=["ENSG1"], rest_client=rest, biomart_client=biomart
    )
    assert names["ENSG1"] == "TP53"
    assert names["ENSG2"] == "fallback name"  # description fallback
    assert rest.calls == 1
    assert biomart.calls == 1


def test_falls_back_when_rest_returns_nothing(tmp_path: Path) -> None:
    rest = FakeRest({})  # no names
    biomart = FakeBiomart(_biomart_frame())
    names = enrich.fetch_gene_names(
        9606, tmp_path, gene_ids=["ENSG1"], rest_client=rest, biomart_client=biomart
    )
    assert "ENSG1" in names
    assert biomart.calls == 1


def test_both_sources_failing_raises(tmp_path: Path) -> None:
    with pytest.raises(MappingError):
        enrich.fetch_gene_names(
            9606,
            tmp_path,
            gene_ids=["ENSG1"],
            rest_client=FakeRest(error=MappingError("REST down")),
            biomart_client=FakeBiomart(error=MappingError("BioMart down")),
        )


def test_result_is_cached_and_reused(tmp_path: Path) -> None:
    enrich.fetch_gene_names(9606, tmp_path, gene_ids=["ENSG1"], rest_client=FakeRest({"ENSG1": "TP53"}))
    rest = FakeRest({"ENSG1": "TP53"})
    names = enrich.fetch_gene_names(9606, tmp_path, gene_ids=["ENSG1"], rest_client=rest)
    assert rest.calls == 0  # served from cache
    assert names["ENSG1"] == "TP53"


def test_force_bypasses_cache(tmp_path: Path) -> None:
    enrich.fetch_gene_names(9606, tmp_path, gene_ids=["ENSG1"], rest_client=FakeRest({"ENSG1": "TP53"}))
    rest = FakeRest({"ENSG1": "TP53"})
    enrich.fetch_gene_names(9606, tmp_path, gene_ids=["ENSG1"], rest_client=rest, force=True)
    assert rest.calls == 1


def test_biomart_only_path_without_gene_ids(tmp_path: Path) -> None:
    """With no node set, REST is skipped and BioMart fetches the whole organism."""
    rest = FakeRest({"ENSG1": "ignored"})
    names = enrich.fetch_gene_names(
        9606, tmp_path, rest_client=rest, biomart_client=FakeBiomart(_biomart_frame())
    )
    assert rest.calls == 0
    assert names["ENSG1"] == "TP53"


def test_build_continues_when_enrichment_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The graph build must never fail because gene names could not be fetched."""
    import hustring.mapping.enrich as enrich_module
    from hustring.graph import build as build_module

    def boom(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise MappingError("all sources down")

    monkeypatch.setattr(enrich_module, "fetch_gene_names", boom)

    annotations: dict[tuple[str | None, str | None, str | None]] = {}
    with pytest.warns(UserWarning, match="gene-name enrichment skipped"):
        build_module._enrich_gene_names(9606, tmp_path, annotations, ["ENSG1"])
    assert annotations == {}
