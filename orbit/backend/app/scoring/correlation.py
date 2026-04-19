"""ORBIT correlation scoring — geographic-exposure-weighted event relevance."""

from __future__ import annotations

import json
import math
import pathlib
from typing import Final

# ---------------------------------------------------------------------------
# Exposure weights — loaded once from data/exposure.json
# ---------------------------------------------------------------------------

_DATA_DIR: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parent.parent.parent / "data"

_EXPOSURE: dict[str, dict[str, float]] = {}


def _load_exposure() -> dict[str, dict[str, float]]:
    """Load exposure weights from JSON, caching in module-level dict."""
    if _EXPOSURE:
        return _EXPOSURE
    path = _DATA_DIR / "exposure.json"
    with path.open("r", encoding="utf-8") as fh:
        raw: dict[str, dict[str, float]] = json.load(fh)
    _EXPOSURE.update(raw)
    return _EXPOSURE


# ---------------------------------------------------------------------------
# Confidence multiplier
# ---------------------------------------------------------------------------


def confidence_multiplier(n: int) -> float:
    """Return a confidence weight based on number of corroborating sources.

    n >= 10 -> 1.0
    n >= 5  -> 0.9
    n >= 2  -> 0.75
    else    -> 0.5
    """
    if n >= 10:
        return 1.0
    if n >= 5:
        return 0.9
    if n >= 2:
        return 0.75
    return 0.5


# ---------------------------------------------------------------------------
# Exposure weight lookup
# ---------------------------------------------------------------------------


def exposure_weight(location: str, ticker: str) -> float:
    """Return the geographic exposure weight for *ticker* in *location*.

    Falls back to 0.0 when the ticker or country code is not mapped.
    """
    exposure = _load_exposure()
    return exposure.get(ticker, {}).get(location, 0.0)


# ---------------------------------------------------------------------------
# Recency decay
# ---------------------------------------------------------------------------


def recency_decay(hours_since_event: float) -> float:
    """Exponential recency decay: exp(-hours / 24).

    Monotonically decreasing for non-negative *hours_since_event*.
    """
    return math.exp(-hours_since_event / 24.0)


# ---------------------------------------------------------------------------
# Single-event relevance
# ---------------------------------------------------------------------------


def relevance(
    location: str,
    ticker: str,
    goldstein_score: float,
    hours_since_event: float,
    num_sources: int,
) -> float:
    """Compute clamped [0, 1] relevance of one event for one ticker.

    Formula::

        exposure_weight(location, ticker)
        * min(1.0, abs(goldstein_score) / 5.0)
        * exp(-hours_since_event / 24.0)
        * confidence_multiplier(num_sources)

    The Goldstein scale is normalised by 5.0 (not 10.0) so that events at
    the |goldstein| >= 5 threshold — which GDELT considers "significant" —
    contribute full intensity.  This keeps low-intensity events muted while
    ensuring that genuinely impactful events can breach the ACT relevance
    threshold (0.55) for tickers with high geographic exposure.
    """
    raw = (
        exposure_weight(location, ticker)
        * min(1.0, abs(goldstein_score) / 5.0)
        * recency_decay(hours_since_event)
        * confidence_multiplier(num_sources)
    )
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Aggregate relevance over multiple events
# ---------------------------------------------------------------------------


def aggregate_relevance(
    relevances: list[float],
) -> float:
    """Aggregate a list of per-event relevance scores for one ticker.

    * ``max_single`` — highest individual relevance.
    * ``top_3_sum`` — sum of the top-3 relevances, capped at 1.0.
    * Returns ``max(max_single, top_3_sum)``, clamped to [0, 1].
    """
    if not relevances:
        return 0.0
    sorted_desc = sorted(relevances, reverse=True)
    max_single = sorted_desc[0]
    top_3_sum = min(1.0, sum(sorted_desc[:3]))
    result = max(max_single, top_3_sum)
    return max(0.0, min(1.0, result))
