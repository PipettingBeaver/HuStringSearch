"""Ensembl REST client, used as the primary source for gene names.

The REST API lives on different infrastructure from BioMart, so it is often up when
BioMart is not, needs no authentication, and supports batched lookups. Like all
enrichment, it is called only at build time and degrades gracefully.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

import requests

from ..errors import MappingError

REST_BASE = "https://rest.ensembl.org"
DEFAULT_BATCH = 500
DEFAULT_WORKERS = 4
RETRY_DELAYS = (1.0, 2.0, 4.0)


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
        """Bulk-lookup genes; unknown IDs map to ``None`` and are dropped.

        One transient failure (timeout, reset, 5xx, bad JSON) must not abort a whole
        batch, so the POST is retried with 1s/2s/4s backoff before giving up.
        """
        if not gene_ids:
            return {}

        max_attempts = len(RETRY_DELAYS) + 1
        for attempt in range(max_attempts):
            if attempt:
                time.sleep(RETRY_DELAYS[attempt - 1])
            try:
                payload = self._post_lookup(gene_ids)
            except MappingError:
                if attempt == max_attempts - 1:
                    raise
            else:
                break

        if not isinstance(payload, dict):
            raise MappingError("Ensembl REST returned an unexpected payload")
        return {
            str(key): value
            for key, value in payload.items()
            if isinstance(value, dict)
        }

    def _post_lookup(self, gene_ids: Sequence[str]) -> object:
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
            payload: object = response.json()
        except ValueError as exc:
            raise MappingError(f"Ensembl REST returned invalid JSON: {exc}") from exc
        except requests.RequestException as exc:
            raise MappingError(f"Ensembl REST request failed: {exc}") from exc
        return payload

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
