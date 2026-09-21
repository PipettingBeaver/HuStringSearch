"""Configuration models for building the graph and running RWR.

Every field carries a ``description`` so the preprocessing/build window can
render an explanation of what each option does, without duplicating text in the
UI. ``describe()`` extracts those descriptions for the frontend.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import ConfigError
from .species import default_sources_for, lookup_species


class NodeGranularity(StrEnum):
    """Whether nodes are genes, proteins/isoforms, or left as provided."""

    GENE = "gene"
    PROTEIN = "protein"
    AS_PROVIDED = "as_provided"


class DedupePolicy(StrEnum):
    """How to combine parallel edges between the same node pair."""

    MAX = "max"
    SUM = "sum"
    MEAN = "mean"


class WeightNormalization(StrEnum):
    """Optional rescaling of merged edge weights before RWR."""

    NONE = "none"
    LINEAR = "linear"
    LOG = "log"


class SourceConfig(BaseModel):
    """One interactome source and how its edges are weighted."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Registered source name, e.g. 'string', 'huri', 'biogrid'.")
    enabled: bool = Field(True, description="Include this source's edges in the merged graph.")
    weight: float = Field(
        1.0,
        gt=0,
        description="Multiplier applied to this source's edge weights before merging.",
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Source-specific options passed to the plugin, e.g. a local file path "
            "for the custom TSV overlay or a species URL for IntAct."
        ),
    )


class BuildConfig(BaseModel):
    """Everything needed to turn raw sources into one canonical weighted graph."""

    taxid: int = Field(
        9606,
        gt=0,
        description="NCBI taxonomy ID of the organism to build (9606 = human).",
    )
    sources: list[SourceConfig] | None = Field(
        None,
        description="Sources to merge. Defaults to the curated preset for the taxon.",
    )
    node_granularity: NodeGranularity = Field(
        NodeGranularity.GENE,
        description=(
            "Node level. 'gene' collapses isoform/protein IDs to one Ensembl Gene ID "
            "(higher connectivity, but merged isoform edges can inflate degree and bias "
            "RWR toward hubs). 'protein' preserves isoforms (sparser; may drop edges with "
            "no gene mapping). 'as_provided' does minimal processing for advanced use."
        ),
    )
    string_score_threshold: int = Field(
        700,
        ge=0,
        le=1000,
        description=(
            "Minimum STRING combined confidence (0-1000) to keep an edge. Higher = more "
            "precise and smaller; lower = more recall and a denser graph."
        ),
    )
    huri_boost: float = Field(
        2.0,
        gt=0,
        description=(
            "Weight multiplier for HuRI edges. HuRI is a high-confidence experimental "
            "binary map, so its edges are boosted relative to STRING confidence scores."
        ),
    )
    id_mapping_strict: bool = Field(
        True,
        description=(
            "If true, drop nodes/edges whose identifiers cannot be mapped to the canonical "
            "space. If false, keep them under their native ID and flag them."
        ),
    )
    drop_self_loops: bool = Field(
        True,
        description="Remove self-edges so a walk cannot trivially reinforce a node.",
    )
    dedupe_policy: DedupePolicy = Field(
        DedupePolicy.MAX,
        description="How to merge multiple edges between the same pair (max/sum/mean).",
    )
    min_node_degree: int = Field(
        0,
        ge=0,
        description="Remove nodes with fewer than this many edges after merging.",
    )
    drop_small_components: int = Field(
        0,
        ge=0,
        description=(
            "Remove connected components smaller than this many nodes (0 = keep all). "
            "Isolated/small components cannot receive meaningful RWR mass."
        ),
    )
    keep_largest_component: bool = Field(
        False,
        description="Keep only the single largest connected component (overrides the size floor).",
    )
    weight_normalization: WeightNormalization = Field(
        WeightNormalization.NONE,
        description=(
            "Rescale merged weights before RWR. 'log' tames very high-confidence edges; "
            "'linear' min-max scales them; 'none' keeps raw weights."
        ),
    )

    @model_validator(mode="after")
    def _fill_sources(self) -> BuildConfig:
        if self.sources is None:
            self.sources = [
                SourceConfig(name=name) for name in default_sources_for(self.taxid)
            ]
        if not any(s.enabled for s in self.sources):
            raise ConfigError("at least one source must be enabled")
        return self

    def enabled_sources(self) -> list[SourceConfig]:
        """Enabled sources, in configuration order."""
        return [s for s in (self.sources or []) if s.enabled]

    def species_name(self) -> str:
        """Human-readable species label for the manifest/UI."""
        preset = lookup_species(self.taxid)
        if preset:
            return f"{preset.scientific_name} ({preset.common_name})"
        return f"taxon {self.taxid}"


class RWRConfig(BaseModel):
    """Parameters of the Random Walk with Restart."""

    restart_prob: float = Field(
        0.85,
        gt=0,
        lt=1,
        description=(
            "Probability of jumping back to the seed(s) each step. Higher = scores stay "
            "local to the target; lower = the walk diffuses further across the graph."
        ),
    )
    max_iter: int = Field(
        1000,
        ge=1,
        description="Maximum power-iteration steps before returning the current scores.",
    )
    tol: float = Field(
        1e-6,
        gt=0,
        description="Stop when the L1 change between iterations falls below this tolerance.",
    )
    normalize_columns: bool = Field(
        True,
        description="Column-normalize the adjacency into a stochastic transition matrix.",
    )
    self_loop_isolated: bool = Field(
        True,
        description=(
            "Give isolated nodes a self-loop so probability is conserved instead of leaking "
            "out of a degree-zero node."
        ),
    )


class SeedConfig(BaseModel):
    """Seed selection: a single target by default, or a weighted set."""

    seeds: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Target identifiers (symbols or Ensembl Gene IDs). One seed is the default; "
            "multiple seeds center the walk on their shared neighborhood, which can blur "
            "specific signals if the seeds are heterogeneous."
        ),
    )
    weights: list[float] | None = Field(
        None,
        description="Optional per-seed weights. If omitted, seeds are weighted uniformly.",
    )

    @model_validator(mode="after")
    def _check_weights(self) -> SeedConfig:
        if self.weights is None:
            return self
        if len(self.weights) != len(self.seeds):
            raise ConfigError("weights length must match seeds length")
        if any(w <= 0 for w in self.weights):
            raise ConfigError("seed weights must be positive")
        return self


def describe(model_cls: type[BaseModel]) -> dict[str, str]:
    """Return {field_name: description} for rendering an explanation panel."""
    return {
        name: (field.description or "")
        for name, field in model_cls.model_fields.items()
    }
