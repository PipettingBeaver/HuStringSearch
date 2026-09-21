"""Shared typing helpers.

``Array`` is a parameterized alias (rather than a bare ``np.ndarray``) so the
annotations satisfy strict mypy across numpy versions, whose stubs differ in
whether ``ndarray`` requires explicit type arguments.
"""

from __future__ import annotations

from typing import Any, TypeAlias

from numpy.typing import NDArray

Array: TypeAlias = NDArray[Any]
