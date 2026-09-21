"""Fetch a prebuilt graph archive (Release asset) and unpack it."""

from __future__ import annotations

import io
import tarfile
import urllib.request
from pathlib import Path

from ..errors import GraphError


def _root_to_strip(names: list[str]) -> str | None:
    """Return the single top-level directory to strip, if the archive has one."""
    entries = [name for name in names if name]
    if not entries:
        return None
    roots = {name.split("/", 1)[0] for name in entries}
    if len(roots) != 1:
        return None
    root = roots.pop()
    if any(name.startswith(root + "/") for name in entries):
        return root
    return None


def _extract(archive: tarfile.TarFile, member: tarfile.TarInfo, dest: Path) -> None:
    try:
        archive.extract(member, dest, filter="data")
    except TypeError:
        archive.extract(member, dest)


def fetch_graph_archive(url: str, dest: str | Path) -> Path:
    """Download a ``.tar.gz`` graph archive and extract it into ``dest``.

    A single top-level directory in the archive is stripped, so an archive laid
    out as ``graph/adjacency.npz`` extracts directly into ``dest``.
    """
    target = Path(dest)
    target.mkdir(parents=True, exist_ok=True)

    try:
        with urllib.request.urlopen(url) as response:
            payload = response.read()
    except OSError as exc:
        raise GraphError(f"failed to download graph archive from {url}: {exc}") from exc

    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            root = _root_to_strip(archive.getnames())
            for member in archive.getmembers():
                name = member.name
                if root is not None:
                    if name == root:
                        continue
                    if name.startswith(root + "/"):
                        name = name[len(root) + 1 :]
                if not name:
                    continue
                member.name = name
                _extract(archive, member, target)
    except tarfile.TarError as exc:
        raise GraphError(f"invalid graph archive from {url}: {exc}") from exc

    if not (target / "adjacency.npz").exists():
        raise GraphError(f"archive from {url} did not contain adjacency.npz")
    return target
