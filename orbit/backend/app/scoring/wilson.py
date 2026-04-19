"""Wilson-score confidence intervals for ORBIT hit-rate tracking."""

from __future__ import annotations

import math
from typing import Final, NamedTuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_Z: Final[float] = 1.96  # 95% confidence level
_MIN_SAMPLE: Final[int] = 20  # minimum n before we publish a CI


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class WilsonResult(NamedTuple):
    """Wilson confidence interval result.

    If *n* <= 20, ``lower`` and ``upper`` are ``None`` (early sample).
    """

    center: float
    lower: float | None
    upper: float | None
    n: int


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def wilson_ci(successes: int, n: int) -> WilsonResult:
    """Compute the Wilson-score confidence interval.

    Parameters
    ----------
    successes:
        Number of "correct" outcomes.
    n:
        Total number of trials.

    Returns
    -------
    WilsonResult
        ``(center, lower, upper, n)``.
        When ``n <= 20`` the bounds are ``None`` (display "n=X (early sample)").
        When ``n == 0`` returns ``(0.0, None, None, 0)``.
    """
    if n <= 0:
        return WilsonResult(center=0.0, lower=None, upper=None, n=0)

    p: float = successes / n
    z2: float = _Z * _Z

    center: float = (p + z2 / (2.0 * n)) / (1.0 + z2 / n)
    margin: float = _Z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n) / (1.0 + z2 / n)

    if n <= _MIN_SAMPLE:
        return WilsonResult(center=center, lower=None, upper=None, n=n)

    lower: float = center - margin
    upper: float = center + margin
    return WilsonResult(center=center, lower=lower, upper=upper, n=n)


def format_wilson(result: WilsonResult) -> str:
    """Human-readable string for a Wilson CI result."""
    if result.lower is None or result.upper is None:
        return f"n={result.n} (early sample)"
    return f"{result.center:.3f} [{result.lower:.3f}, {result.upper:.3f}] (n={result.n})"
