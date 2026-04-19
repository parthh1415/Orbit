"""ORBIT scorecard routes — backtest and live performance metrics."""

from __future__ import annotations

import json
import math
import pathlib
from typing import Final

import aiosqlite
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.config import TRACKED_TICKERS
from app.db import get_db
from app.schemas import ScorecardRow
from app.scoring.wilson import WilsonResult, wilson_ci

router = APIRouter(prefix="/api/scorecard", tags=["scorecard"])

# ---------------------------------------------------------------------------
# Backtest data — loaded once
# ---------------------------------------------------------------------------

_DATA_DIR: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parent.parent.parent / "data"
_BACKTEST_CACHE: list[ScorecardRow] | None = None


def _load_backtest() -> list[ScorecardRow]:
    """Load backtest results from JSON, cached after first call."""
    global _BACKTEST_CACHE
    if _BACKTEST_CACHE is not None:
        return _BACKTEST_CACHE

    path = _DATA_DIR / "backtest_results.json"
    with path.open("r", encoding="utf-8") as fh:
        raw: dict[str, dict[str, float]] = json.load(fh)

    rows: list[ScorecardRow] = []
    for ticker, stats in raw.items():
        act_n = int(stats.get("act_n", 0))
        hit_rate = float(stats.get("act_hit_rate", 0.0))
        wins = round(act_n * hit_rate)
        losses = act_n - wins
        avg_return = round(hit_rate - 0.5, 4)  # simplified proxy
        sharpe = round((hit_rate - 0.5) / 0.15, 2) if hit_rate > 0 else 0.0
        rows.append(
            ScorecardRow(
                ticker=ticker,
                total_trades=act_n,
                wins=wins,
                losses=losses,
                win_rate=round(hit_rate * 100, 1),
                avg_return=round(avg_return * 100, 1),
                sharpe=sharpe,
            )
        )

    _BACKTEST_CACHE = rows
    return _BACKTEST_CACHE


# ---------------------------------------------------------------------------
# Live scorecard response model
# ---------------------------------------------------------------------------


class LiveScorecardRow(BaseModel):
    """One row in the live scorecard: base scorecard fields plus Wilson CI."""

    model_config = ConfigDict(strict=True, frozen=True)

    # Base scorecard fields (same schema the frontend expects)
    ticker: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_return: float
    sharpe: float

    # Wilson CI extras
    wilson_center: float
    wilson_lower: float | None
    wilson_upper: float | None
    wilson_n: int


# ---------------------------------------------------------------------------
# Helper — compute sharpe from returns list
# ---------------------------------------------------------------------------


def _sharpe(returns: list[float]) -> float:
    """Compute Sharpe ratio from a list of forward returns.

    Returns ``mean / std`` rounded to 2 decimals, or ``0.0`` when the
    standard deviation is zero (or the list is empty).
    """
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0.0:
        return 0.0
    return round(mean / std, 2)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/backtest", response_model=list[ScorecardRow])
async def get_backtest() -> list[ScorecardRow]:
    """Return backtest scorecard rows (loaded once from JSON)."""
    return _load_backtest()


@router.get("/live", response_model=list[LiveScorecardRow])
async def get_live_scorecard() -> list[LiveScorecardRow]:
    """Compute live scorecard from outcomes table using Wilson CI.

    Always returns one row per tracked ticker (AAPL, NVDA, TSM), even when
    a ticker has zero outcomes yet.  The response includes the same base
    fields the backtest endpoint returns (``win_rate``, ``total_trades``,
    ``avg_return``, ``sharpe``) **plus** Wilson CI bounds.
    """
    # --- aggregate counts per ticker ---
    async with get_db() as conn:
        cursor: aiosqlite.Cursor = await conn.execute(
            """
            SELECT t.ticker,
                   COUNT(*)                     AS total,
                   SUM(o.directionally_correct) AS wins
            FROM outcomes o
            JOIN trades t ON t.id = o.trade_id
            GROUP BY t.ticker
            ORDER BY t.ticker
            """
        )
        agg_rows = await cursor.fetchall()

        # --- collect per-ticker forward_return values for avg & sharpe ---
        ret_cursor: aiosqlite.Cursor = await conn.execute(
            """
            SELECT t.ticker, o.forward_return
            FROM outcomes o
            JOIN trades t ON t.id = o.trade_id
            ORDER BY t.ticker
            """
        )
        ret_rows = await ret_cursor.fetchall()

    # Build lookup maps
    ticker_stats: dict[str, tuple[int, int]] = {}
    for row in agg_rows:
        ticker_stats[str(row[0])] = (int(row[1]), int(row[2]))

    ticker_returns: dict[str, list[float]] = {}
    for row in ret_rows:
        ticker_returns.setdefault(str(row[0]), []).append(float(row[1]))

    # Build one row per tracked ticker
    results: list[LiveScorecardRow] = []
    for ticker in TRACKED_TICKERS:
        total, wins = ticker_stats.get(ticker, (0, 0))
        losses = total - wins
        win_rate = round((wins / total) * 100, 1) if total > 0 else 0.0

        returns = ticker_returns.get(ticker, [])
        avg_ret = round((sum(returns) / len(returns)) * 100, 1) if returns else 0.0
        sharpe = _sharpe(returns)

        w: WilsonResult = wilson_ci(wins, total)
        results.append(
            LiveScorecardRow(
                ticker=ticker,
                total_trades=total,
                wins=wins,
                losses=losses,
                win_rate=win_rate,
                avg_return=avg_ret,
                sharpe=sharpe,
                wilson_center=round(w.center, 2),
                wilson_lower=round(w.lower, 2) if w.lower is not None else None,
                wilson_upper=round(w.upper, 2) if w.upper is not None else None,
                wilson_n=w.n,
            )
        )
    return results
