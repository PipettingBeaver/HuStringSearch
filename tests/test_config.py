"""Configuration defaults, species generality, and the UI description registry."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hustring.config import BuildConfig, NodeGranularity, SeedConfig, describe
from hustring.species import default_sources_for, lookup_species


def test_human_defaults() -> None:
    cfg = BuildConfig()
    assert cfg.taxid == 9606
    assert [s.name for s in cfg.enabled_sources()] == ["huri", "string"]
    assert cfg.node_granularity is NodeGranularity.GENE


def test_non_human_is_not_huri() -> None:
    cfg = BuildConfig(taxid=511145)
    assert [s.name for s in cfg.enabled_sources()] == ["string"]
    assert "Escherichia" in cfg.species_name()


def test_unknown_taxon_still_builds() -> None:
    cfg = BuildConfig(taxid=999999)
    assert [s.name for s in cfg.enabled_sources()] == ["string"]
    assert "999999" in cfg.species_name()


def test_describe_covers_every_field() -> None:
    descriptions = describe(BuildConfig)
    assert set(descriptions) == set(BuildConfig.model_fields)
    assert all(descriptions.values())


def test_disabling_all_sources_rejected() -> None:
    with pytest.raises(ValidationError):
        BuildConfig(sources=[{"name": "string", "enabled": False}])


def test_seed_weight_length_mismatch_rejected() -> None:
    with pytest.raises(ValidationError):
        SeedConfig(seeds=["A", "B"], weights=[1.0])


def test_curated_presets_are_unique_and_consistent() -> None:
    assert lookup_species(9606) is not None
    assert lookup_species(10090) is not None
    assert default_sources_for(9606) == ("huri", "string")
    assert default_sources_for(7227) == ("string",)
