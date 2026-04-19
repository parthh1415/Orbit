"""ORBIT portfolio routes — open positions and summary."""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter

from app.db import get_db
from app.schemas import DirectionEnum, PortfolioSummary, Position

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

STARTING_CAPITAL: float = 100_000.0

# SQL fragment: resolve the best available price for a trade's ticker.
# Priority: price_cache (updated by replay engine) > latest bar close > entry_price.
_CURRENT_PRICE_SQL = """
    COALESCE(
        (SELECT pc.price FROM price_cache pc WHERE pc.ticker = t.ticker),
        (SELECT b.close FROM bars b
         WHERE b.ticker = t.ticker
         ORDER BY b.timestamp DESC LIMIT 1),
        t.entry_price
    )
"""


@router.get("/positions", response_model=list[Position])
async def get_positions() -> list[Position]:
    """Return all open trades as position summaries."""
    async with get_db() as conn:
        # Open trades: exit_price IS NULL
        cursor: aiosqlite.Cursor = await conn.execute(
            f"""
            SELECT t.ticker, t.direction, t.size_shares, t.entry_price,
                   {_CURRENT_PRICE_SQL} AS current_price
            FROM trades t
            WHERE t.exit_price IS NULL AND t.size_shares > 0
            ORDER BY t.executed_at DESC
            """
        )
        rows = await cursor.fetchall()

    positions: list[Position] = []
    for row in rows:
        ticker = str(row[0])
        direction = DirectionEnum(str(row[1]))
        size_shares = int(row[2])
        entry_price = round(float(row[3]), 2)
        current_price = round(float(row[4]), 2) if row[4] is not None else entry_price

        if direction == DirectionEnum.LONG:
            unrealized = round((current_price - entry_price) * size_shares, 2)
        elif direction == DirectionEnum.SHORT:
            unrealized = round((entry_price - current_price) * size_shares, 2)
        else:
            unrealized = 0.0

        positions.append(
            Position(
                ticker=ticker,
                direction=direction,
                size_shares=size_shares,
                entry_price=entry_price,
                current_price=current_price,
                unrealized_pnl=unrealized,
            )
        )
    return positions


@router.get("/summary", response_model=PortfolioSummary)
async def get_summary() -> PortfolioSummary:
    """Return aggregate portfolio statistics."""
    async with get_db() as conn:
        # Capital deployed = sum(entry_price * size_shares) for open trades
        cursor: aiosqlite.Cursor = await conn.execute(
            """
            SELECT COALESCE(SUM(entry_price * size_shares), 0.0)
            FROM trades
            WHERE exit_price IS NULL AND size_shares > 0
            """
        )
        row = await cursor.fetchone()
        capital_deployed = round(float(row[0]), 2) if row else 0.0

        # Open position count
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM trades WHERE exit_price IS NULL AND size_shares > 0"
        )
        row = await cursor.fetchone()
        open_positions = int(row[0]) if row else 0

        # Closed position count
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM trades WHERE exit_price IS NOT NULL AND size_shares > 0"
        )
        row = await cursor.fetchone()
        closed_positions = int(row[0]) if row else 0

        # Realized P&L from closed trades
        cursor = await conn.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0.0) FROM trades WHERE exit_price IS NOT NULL AND size_shares > 0"
        )
        row = await cursor.fetchone()
        realized_pnl = round(float(row[0]), 2) if row else 0.0

        # Unrealized P&L from open trades using best available price
        cursor = await conn.execute(
            f"""
            SELECT COALESCE(SUM(
                CASE WHEN t.direction = 'long'
                     THEN ({_CURRENT_PRICE_SQL} - t.entry_price) * t.size_shares
                     WHEN t.direction = 'short'
                     THEN (t.entry_price - {_CURRENT_PRICE_SQL}) * t.size_shares
                     ELSE 0.0
                END
            ), 0.0) FROM trades t WHERE t.exit_price IS NULL AND t.size_shares > 0
            """
        )
        row = await cursor.fetchone()
        unrealized_pnl = round(float(row[0]), 2) if row else 0.0

    total_pnl = round(realized_pnl + unrealized_pnl, 2)
    capital_available = round(STARTING_CAPITAL - capital_deployed, 2)

    return PortfolioSummary(
        capital_total=STARTING_CAPITAL,
        capital_deployed=capital_deployed,
        capital_available=capital_available,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        total_pnl=total_pnl,
        open_positions=open_positions,
        closed_positions=closed_positions,
    )
