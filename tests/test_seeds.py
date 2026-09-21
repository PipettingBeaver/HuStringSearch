"""Seed resolution and restart-vector behavior."""

from __future__ import annotations

import pytest

from hustring.core.seeds import resolve_seeds, restart_vector
from hustring.errors import SeedError


def test_uniform_restart_vector() -> None:
    vector = restart_vector(4, [0, 2])
    assert vector.tolist() == pytest.approx([0.5, 0.0, 0.5, 0.0])


def test_weighted_restart_vector() -> None:
    vector = restart_vector(3, [0, 1], [3.0, 1.0])
    assert vector[0] == pytest.approx(0.75)
    assert vector[1] == pytest.approx(0.25)


def test_resolve_reports_missing() -> None:
    result = resolve_seeds(["A", "B", "C"], ["B", "Z"])
    assert result.indices == [1]
    assert result.resolved == ["B"]
    assert result.missing == ["Z"]
    assert result.has_missing


def test_resolve_keeps_aligned_weights() -> None:
    result = resolve_seeds(["A", "B", "C"], ["A", "Z", "C"], [1.0, 9.0, 4.0])
    assert result.indices == [0, 2]
    assert result.weights == [1.0, 4.0]


def test_resolve_all_missing_raises() -> None:
    with pytest.raises(SeedError):
        resolve_seeds(["A"], ["Z"])


def test_restart_vector_requires_seeds() -> None:
    with pytest.raises(SeedError):
        restart_vector(3, [])


def test_restart_vector_rejects_nonpositive_weights() -> None:
    with pytest.raises(SeedError):
        restart_vector(3, [0, 1], [1.0, 0.0])
