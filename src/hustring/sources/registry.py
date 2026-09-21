"""Source registry: name -> class, plus construction from SourceConfig."""

from __future__ import annotations

from ..config import SourceConfig
from ..errors import SourceError
from .base import InteractomeSource

_REGISTRY: dict[str, type[InteractomeSource]] = {}


def register(cls: type[InteractomeSource]) -> type[InteractomeSource]:
    """Class decorator that adds a source to the registry."""
    name = cls.metadata.name
    if name in _REGISTRY and _REGISTRY[name] is not cls:
        raise SourceError(f"duplicate source name '{name}'")
    _REGISTRY[name] = cls
    return cls


def available_sources() -> tuple[str, ...]:
    """Registered source names, sorted."""
    return tuple(sorted(_REGISTRY))


def get_source_class(name: str) -> type[InteractomeSource]:
    """Look up a source class by name."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise SourceError(
            f"unknown source '{name}'; available: {list(available_sources())}"
        ) from exc


def create_source(config: SourceConfig) -> InteractomeSource:
    """Instantiate a source from its configuration, passing through options."""
    cls = get_source_class(config.name)
    try:
        return cls(**config.options)
    except TypeError as exc:
        raise SourceError(f"invalid options for source '{config.name}': {exc}") from exc
