"""Pluggable interactome sources.

Importing this package registers all built-in sources.
"""

from __future__ import annotations

from .base import (
    EDGE_COLUMNS,
    NODE_COLUMNS,
    DownloadSpec,
    InteractomeSource,
    SourceData,
    SourceMetadata,
)
from .biogrid import BiogridSource
from .custom_tsv import CustomTSVSource
from .huri import HuriSource
from .intact import IntactSource
from .orthology import OrthologyBridge
from .registry import (
    available_sources,
    create_source,
    get_source_class,
    register,
)
from .string import StringSource

__all__ = [
    "EDGE_COLUMNS",
    "NODE_COLUMNS",
    "BiogridSource",
    "CustomTSVSource",
    "DownloadSpec",
    "HuriSource",
    "IntactSource",
    "InteractomeSource",
    "OrthologyBridge",
    "SourceData",
    "SourceMetadata",
    "StringSource",
    "available_sources",
    "create_source",
    "get_source_class",
    "register",
]
