"""Ensembl REST client, used as the primary source for gene names.

The REST API lives on different infrastructure from BioMart, so it is often up when
BioMart is not, needs no authentication, and supports batched lookups. Like all
enrichment, it is called only at build time and degrades gracefully.
"""

from __future__ import annotations

from collections.abc import Sequence

import requests

from ..errors import MappingError

REST_BASE = "https://rest.ensembl.org"
DEFAULT_BATCH = 500
DEFAULT_WORKERS = 4


def _clean_name(record: dict[str, object]) -> str:
    """Prefer the descriptive name ("tumor protein p53") over the bare symbol."""
    description = record.get("description")
    if isinstance(description, str) and description.strip():
        return description.split(" [Source:")[0].strip()
    display = record.get("display_name")
    if isinstance(display, str) and display.strip():
        return display.strip()
    return ""


class EnsemblRestClient:
    """Minimal client for the Ensembl REST API."""

    def __init__(self, base_url: str = REST_BASE, *, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def lookup_ids(self, gene_ids: Sequence[str]) -> dict[str, dict[str, object]]:
        """Bulk-lookup genes; unknown IDs map to ``None`` and are dropped."""
        if not gene_ids:
            return {}
        try:
            response = requests.post(
                f"{self.base_url}/lookup/id",
                json={"ids": list(gene_ids)},
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "HuStringSearch/0.0.1",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise MappingError(f"Ensembl REST request failed: {exc}") from exc
        except ValueError as exc:
            raise MappingError(f"Ensembl REST returned invalid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise MappingError("Ensembl REST returned an unexpected payload")
        return {
            str(key): value
            for key, value in payload.items()
            if isinstance(value, dict)
        }

    def gene_names(
        self,
        gene_ids: Sequence[str],
        *,
        batch_size: int = DEFAULT_BATCH,
        max_workers: int = DEFAULT_WORKERS,
    ) -> dict[str, str]:
        """Return {gene_id: display name} for the genes that resolve.

        Batches are sent concurrently (bounded by ``max_workers``) to keep a
        whole-organism build to a sensible time; the REST API is rate limited, so
        keep the worker count modest.
        """
        mapping: dict[str, str] = {}
        ids = list(gene_ids)
        batches = [
            ids[start : start + batch_size]
            for start in range(0, len(ids), batch_size)
        ]
        if not batches:
            return mapping

        def resolve(batch: list[str]) -> dict[str, str]:
            resolved: dict[str, str] = {}
            for gene_id, record in self.lookup_ids(batch).items():
                name = _clean_name(record)
                if name:
                    resolved[gene_id] = name
            return resolved

        if len(batches) == 1:
            return resolve(batches[0])

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for resolved in pool.map(resolve, batches):
                mapping.update(resolved)
        return mapping
