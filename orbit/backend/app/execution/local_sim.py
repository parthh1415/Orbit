"""ORBIT paper-trade executor — simulates fills against latest bar data."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

import aiosqlite

from app.config import Settings
from app.db import get_db
from app.schemas import DirectionEnum, Trade

# Slippage: 2 basis points
_SLIPPAGE_BPS: float = 0.0002


async def execute_paper_trade(
    ticker: str,
    direction: DirectionEnum,
    settings: Settings,
    *,
    size_shares: int = 0,
    size_notional: float = 0.0,
) -> Trade:
    """Execute a paper trade against the latest bar close price.

    Steps
    -----
    1. Fetch latest bar close for *ticker* as the mid price.
    2. Apply 2 bps slippage in trade direction (BUY: +, SELL: -).
    3. If *size_shares* > 0, use it directly; otherwise compute from
       ``floor(size_notional / fill_price)``.
    4. Insert trade row into SQLite.
    5. Return the ``Trade`` object.

    Raises
    ------
    ValueError
        If no bars exist for the ticker or both size fields are non-positive.
    """
    if size_shares <= 0 and size_notional <= 0:
        msg = f"size_shares or size_notional must be positive, got shares={size_shares} notional={size_notional}"
        raise ValueError(msg)

    async with get_db(settings.database_url) as conn:
        cursor: aiosqlite.Cursor = await conn.execute(
            "SELECT close FROM bars WHERE ticker = ? ORDER BY timestamp DESC LIMIT 1",
            (ticker,),
        )
        row = await cursor.fetchone()
        if row is None:
            msg = f"No bar data for ticker {ticker}"
            raise ValueError(msg)

        mid_price: float = float(row[0])

        # Apply slippage
        if direction == DirectionEnum.LONG:
            fill_price = mid_price * (1.0 + _SLIPPAGE_BPS)
        elif direction == DirectionEnum.SHORT:
            fill_price = mid_price * (1.0 - _SLIPPAGE_BPS)
        else:
            fill_price = mid_price

        fill_price = round(fill_price, 2)
        computed_shares: int = (
            size_shares
            if size_shares > 0
            else (math.floor(size_notional / fill_price) if fill_price > 0 else 0)
        )

        trade_id = uuid.uuid4().hex
        # We need a verdict_id — create a placeholder verdict for paper trades
        verdict_id = uuid.uuid4().hex
        now_iso = datetime.now(tz=UTC).isoformat()

        # Insert placeholder verdict
        await conn.execute(
            """
            INSERT INTO verdicts (id, ticker, verdict_class, direction,
                                  relevance_score, issued_at, verdict_object)
            VALUES (?, ?, 'hold', ?, 0.0, ?, '{}')
            """,
            (verdict_id, ticker, direction.value, now_iso),
        )

        # Insert trade
        await conn.execute(
            """
            INSERT INTO trades (id, verdict_id, ticker, direction,
                                size_shares, entry_price, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (trade_id, verdict_id, ticker, direction.value, computed_shares, fill_price, now_iso),
        )
        await conn.commit()

    return Trade(
        id=trade_id,
        verdict_id=verdict_id,
        ticker=ticker,
        direction=direction,
        size_shares=computed_shares,
        entry_price=fill_price,
        executed_at=datetime.fromisoformat(now_iso),
    )
