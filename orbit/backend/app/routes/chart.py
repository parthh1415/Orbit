"""ORBIT bars routes — OHLCV bar data for tracked tickers."""

from __future__ import annotations

from datetime import datetime

import aiosqlite
from fastapi import APIRouter, HTTPException, Query

from app.config import TRACKED_TICKERS
from app.db import get_db
from app.schemas import Bar

router = APIRouter(prefix="/api/bars", tags=["bars"])


@router.get("/{ticker}", response_model=list[Bar])
async def get_bars(
    ticker: str,
    timeframe: str = Query(default="1Min", description="Bar timeframe"),
    limit: int = Query(default=500, ge=1, le=5000, description="Max bars to return"),
) -> list[Bar]:
    """Return up to *limit* most recent bars for *ticker*."""
    _ = timeframe  # reserved for future multi-timeframe support
    if ticker not in TRACKED_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown ticker '{ticker}'. Must be one of {list(TRACKED_TICKERS)}",
        )

    async with get_db() as conn:
        cursor: aiosqlite.Cursor = await conn.execute(
            """
            SELECT ticker, timestamp, open, high, low, close, volume
            FROM bars
            WHERE ticker = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (ticker, limit),
        )
        rows = await cursor.fetchall()

    # Reverse to chronological order (query returns newest first)
    ordered = list(reversed(list(rows)))
    bars: list[Bar] = [
        Bar(
            ticker=str(row[0]),
            timestamp=datetime.fromisoformat(str(row[1])),
            open=round(float(row[2]), 2),
            high=round(float(row[3]), 2),
            low=round(float(row[4]), 2),
            close=round(float(row[5]), 2),
            volume=int(row[6]),
        )
        for row in ordered
    ]
    return bars
