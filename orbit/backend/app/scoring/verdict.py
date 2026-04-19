"""ORBIT deterministic verdict engine — NO LLM, pure threshold logic."""

from __future__ import annotations

import json
import pathlib
import uuid
from datetime import UTC, datetime
from typing import Final

from app.schemas import DirectionEnum, VerdictClass, VerdictObject

# ---------------------------------------------------------------------------
# Backtest results — loaded once from data/backtest_results.json
# ---------------------------------------------------------------------------

_DATA_DIR: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parent.parent.parent / "data"

_BACKTEST: dict[str, dict[str, float]] = {}


def _load_backtest() -> dict[str, dict[str, float]]:
    """Load backtest results from JSON, caching in module-level dict."""
    if _BACKTEST:
        return _BACKTEST
    path = _DATA_DIR / "backtest_results.json"
    with path.open("r", encoding="utf-8") as fh:
        raw: dict[str, dict[str, float]] = json.load(fh)
    _BACKTEST.update(raw)
    return _BACKTEST


# ---------------------------------------------------------------------------
# Direction from Goldstein sign
# ---------------------------------------------------------------------------

_GOLDSTEIN_NEAR_ZERO_THRESHOLD: Final[float] = 1.0


def direction_from_goldstein(goldstein_score: float) -> DirectionEnum:
    """Derive trade direction from the Goldstein score sign.

    * Negative  -> SHORT (bearish)
    * Positive  -> LONG  (bullish)
    * Near-zero (abs < 1.0) -> FLAT  (contributes to WAIT)
    """
    if abs(goldstein_score) < _GOLDSTEIN_NEAR_ZERO_THRESHOLD:
        return DirectionEnum.FLAT
    if goldstein_score < 0:
        return DirectionEnum.SHORT
    return DirectionEnum.LONG


# ---------------------------------------------------------------------------
# Verdict classification
# ---------------------------------------------------------------------------

_ACT_RELEVANCE_THRESHOLD: Final[float] = 0.55
_WAIT_RELEVANCE_LOWER: Final[float] = 0.30
_ACT_HIT_RATE_THRESHOLD: Final[float] = 0.54
_WAIT_HIT_RATE_LOWER: Final[float] = 0.50
_ACT_MAX_CONTRADICTING: Final[int] = 1


def _verdict_class_to_schema(
    verdict_class: str,
    direction: DirectionEnum,
) -> VerdictClass:
    """Map internal verdict class string + direction to the schema enum.

    ACT + LONG  -> STRONG_BUY or BUY
    ACT + SHORT -> STRONG_SELL or SELL
    WAIT / IGNORE -> HOLD
    """
    if verdict_class == "ACT":
        if direction == DirectionEnum.LONG:
            return VerdictClass.BUY
        if direction == DirectionEnum.SHORT:
            return VerdictClass.SELL
        return VerdictClass.HOLD
    return VerdictClass.HOLD


def compute_verdict(
    ticker: str,
    aggregated_score: float,
    goldstein_score: float,
    contradicting_count: int,
    has_active_position: bool,
    *,
    top_event: str = "",
    top_score: float = 0.0,
    exposure_code: str = "",
    exposure_weight_pct: float = 0.0,
) -> VerdictObject:
    """Produce a deterministic verdict for *ticker*.

    Thresholds
    ----------
    ACT:    score >= 0.55 AND backtest hit_rate >= 54% AND contradicting <= 1
    WAIT:   score in [0.30, 0.55) OR contradicting >= 2 OR hit_rate in [50%, 54%)
    IGNORE: score < 0.30 AND no active position
    """
    backtest = _load_backtest()
    ticker_bt = backtest.get(ticker, {})
    hit_rate: float = ticker_bt.get("act_hit_rate", 0.0)
    act_n: int = int(ticker_bt.get("act_n", 0))

    direction = direction_from_goldstein(goldstein_score)

    # Determine verdict class string
    verdict_label: str
    reason = ""
    if (
        aggregated_score >= _ACT_RELEVANCE_THRESHOLD
        and hit_rate >= _ACT_HIT_RATE_THRESHOLD
        and contradicting_count <= _ACT_MAX_CONTRADICTING
        and direction != DirectionEnum.FLAT
    ):
        verdict_label = "ACT"
    elif (
        (_WAIT_RELEVANCE_LOWER <= aggregated_score < _ACT_RELEVANCE_THRESHOLD)
        or contradicting_count >= 2
        or (_WAIT_HIT_RATE_LOWER <= hit_rate < _ACT_HIT_RATE_THRESHOLD)
        or direction == DirectionEnum.FLAT
    ):
        verdict_label = "WAIT"
        if direction == DirectionEnum.FLAT:
            reason = "Direction unclear — Goldstein near zero"
        elif contradicting_count >= 2:
            reason = f"Contradicting signals ({contradicting_count} opposing events)"
        elif aggregated_score < _ACT_RELEVANCE_THRESHOLD:
            reason = "Relevance score below ACT threshold"
        else:
            reason = "Backtest hit rate below confidence threshold"
    elif aggregated_score < _WAIT_RELEVANCE_LOWER and not has_active_position:
        verdict_label = "IGNORE"
        reason = "Low relevance and no active position"
    else:
        # Fallback — active position with low score => WAIT rather than IGNORE
        verdict_label = "WAIT"
        reason = "Active position — monitoring"

    schema_class = _verdict_class_to_schema(verdict_label, direction)

    verdict_meta: dict[str, str] = {
        "label": verdict_label,
        "hit_rate": f"{hit_rate * 100:.1f}%",
        "contradicting_count": str(contradicting_count),
        "top_event": top_event,
        "top_score": str(round(top_score, 2)),
        "exposure_code": exposure_code,
        "exposure_weight": f"{exposure_weight_pct * 100:.0f}%",
        "n_analogs": str(act_n),
    }
    if reason:
        verdict_meta["reason"] = reason

    return VerdictObject(
        id=uuid.uuid4().hex,
        ticker=ticker,
        verdict_class=schema_class,
        direction=direction,
        relevance_score=aggregated_score,
        issued_at=datetime.now(tz=UTC),
        verdict_object=verdict_meta,
    )
