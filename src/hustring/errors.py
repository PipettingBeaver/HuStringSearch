"""Shared exception types."""

from __future__ import annotations


class HuStringError(Exception):
    """Base class for all HuStringSearch errors."""


class ConfigError(HuStringError, ValueError):
    """Raised when a build/RWR/seed configuration is invalid.

    Subclasses ``ValueError`` so pydantic validators surface it as a normal
    ``ValidationError``.
    """


class SourceError(HuStringError):
    """Raised when an interactome source cannot be fetched or parsed."""


class MappingError(HuStringError):
    """Raised when identifiers cannot be harmonized."""


class GraphError(HuStringError):
    """Raised when the merged graph is malformed (e.g. unknown node)."""


class SeedError(GraphError):
    """Raised when seeds cannot be resolved against a graph."""
