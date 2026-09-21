"""Streaming download helper with partial-file safety."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

import requests

from ..errors import SourceError
from .base import DownloadSpec

USER_AGENT = "HuStringSearch/0.0.1 (interactome merge + RWR)"
CHUNK = 1 << 20


def _looks_complete(path: Path, spec: DownloadSpec) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    if spec.expected_bytes is not None:
        return path.stat().st_size == spec.expected_bytes
    return True


def _download(spec: DownloadSpec, target: Path, timeout: float) -> None:
    headers = {"User-Agent": USER_AGENT, **dict(spec.headers)}
    part = target.with_name(target.name + ".part")
    try:
        with requests.get(spec.url, headers=headers, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            with part.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=CHUNK):
                    if chunk:
                        handle.write(chunk)
    except requests.RequestException as exc:
        part.unlink(missing_ok=True)
        raise SourceError(f"failed to download {spec.url}: {exc}") from exc

    if spec.expected_bytes is not None and part.stat().st_size != spec.expected_bytes:
        size = part.stat().st_size
        part.unlink(missing_ok=True)
        raise SourceError(
            f"size mismatch for {spec.url}: got {size}, expected {spec.expected_bytes}"
        )
    os.replace(part, target)


def download_files(
    specs: Sequence[DownloadSpec],
    dest_dir: Path,
    *,
    force: bool = False,
    timeout: float = 120.0,
) -> dict[str, Path]:
    """Download every spec into ``dest_dir``, returning {filename: path}."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, Path] = {}
    for spec in specs:
        target = dest_dir / spec.filename
        if not force and _looks_complete(target, spec):
            resolved[spec.filename] = target
            continue
        if not spec.required:
            try:
                _download(spec, target, timeout)
            except SourceError:
                continue
            resolved[spec.filename] = target
            continue
        _download(spec, target, timeout)
        resolved[spec.filename] = target
    return resolved
