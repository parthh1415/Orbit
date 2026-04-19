"""ORBIT stats route — Bayesian + Kelly + EWMA per ticker."""

from __future__ import annotations

import json
import pathlib
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import TRACKED_TICKERS, get_settings
from app.db import get_db
from app.scoring.stats import bayesian_hit_rate, ewma_stress, kelly_position_size

router = APIRouter(prefix="/api/stats", tags=["stats"])

_DATA_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent.parent / "data"


def _load_backtest() -> dict[str, dict[str, float]]:
    path = _DATA_DIR / "backtest_results.json"
    with path.open("r", encoding="utf-8") as fh:
        data: dict[str, dict[str, float]] = json.load(fh)
    return data


@router.get("/{ticker}")
async def get_stats(ticker: str) -> dict[str, Any]:
    """Return Bayesian hit rate, Kelly sizing, and EWMA stress for *ticker*."""
    if ticker not in TRACKED_TICKERS:
        raise HTTPException(status_code=400, detail=f"Unknown ticker: {ticker}")

    settings = get_settings()
    backtest = _load_backtest()
    bt = backtest.get(ticker, {})
    bt_wins = int(bt.get("act_n", 0) * bt.get("act_hit_rate", 0.5))
    bt_losses = int(bt.get("act_n", 0)) - bt_wins

    # Recent wins/losses from outcomes
    recent_wins = 0
    recent_losses = 0
    async with get_db(settings.database_url) as db:
        cursor = await db.execute(
            """SELECT directionally_correct FROM outcomes o
               JOIN trades t ON o.trade_id = t.id
               WHERE t.ticker = ?
               ORDER BY o.computed_at DESC LIMIT 10""",
            (ticker,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            if row[0]:
                recent_wins += 1
            else:
                recent_losses += 1

    # Available capital
    async with get_db(settings.database_url) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(entry_price * size_shares), 0) FROM trades WHERE exit_price IS NULL AND size_shares > 0"
        )
        deployed_row = await cursor.fetchone()
        deployed = float(deployed_row[0]) if deployed_row and deployed_row[0] else 0.0
    available = 100000.0 - deployed

    # Current price
    price = 100.0
    async with get_db(settings.database_url) as db:
        cursor = await db.execute(
            "SELECT price FROM price_cache WHERE ticker = ?", (ticker,)
        )
        price_row = await cursor.fetchone()
        if price_row:
            price = float(price_row[0])

    # Avg win/loss pct from closed trades
    avg_win = 0.015
    avg_loss = 0.008
    async with get_db(settings.database_url) as db:
        cursor = await db.execute(
            """SELECT direction, entry_price, exit_price FROM trades
               WHERE ticker = ? AND exit_price IS NOT NULL AND size_shares > 0""",
            (ticker,),
        )
        closed = await cursor.fetchall()
        wins_pct: list[float] = []
        losses_pct: list[float] = []
        for row in closed:
            direction, entry, exit_p = str(row[0]), float(row[1]), float(row[2])
            if entry == 0:
                continue
            ret = (exit_p - entry) / entry if direction == "long" else (entry - exit_p) / entry
            if ret > 0:
                wins_pct.append(ret)
            else:
                losses_pct.append(abs(ret))
        if wins_pct:
            avg_win = sum(wins_pct) / len(wins_pct)
        if losses_pct:
            avg_loss = sum(losses_pct) / len(losses_pct)

    # EWMA from recent event scores
    event_scores: list[float] = []
    async with get_db(settings.database_url) as db:
        cursor = await db.execute(
            """SELECT relevance FROM event_scores
               WHERE ticker = ?
               ORDER BY computed_at DESC LIMIT 20""",
            (ticker,),
        )
        rows = await cursor.fetchall()
        event_scores = [float(r[0]) for r in list(rows)[::-1]]

    bay = bayesian_hit_rate(bt_wins, bt_losses, recent_wins, recent_losses)
    kel = kelly_position_size(bay["effective_hit_rate"], avg_win, avg_loss, available, price)
    ewma = ewma_stress(event_scores)

    return {"bayesian": bay, "kelly": kel, "ewma": ewma}
