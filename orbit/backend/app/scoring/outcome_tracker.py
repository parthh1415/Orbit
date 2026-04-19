"""ORBIT outcome tracker — cron job that evaluates closed trades against verdicts."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import aiosqlite

from app.config import Settings
from app.db import get_db


async def track_outcomes(settings: Settings) -> int:
    """Evaluate closed trades and write directional-correctness outcomes.

    For each trade that has been closed (``exit_price IS NOT NULL``) but does
    not yet have an outcome row, compute:

    * ``forward_return`` — ``(exit_price - entry_price) / entry_price``
    * ``directionally_correct`` — whether the sign of the return matches
      the verdict direction (LONG expects positive, SHORT expects negative).

    Returns
    -------
    int
        Number of new outcome rows written.
    """
    written = 0
    async with get_db(settings.database_url) as conn:
        # Find closed trades that lack an outcome row.
        query = """
            SELECT t.id         AS trade_id,
                   t.verdict_id AS verdict_id,
                   t.ticker     AS ticker,
                   t.direction  AS direction,
                   t.entry_price AS entry_price,
                   t.exit_price  AS exit_price,
                   t.closed_at   AS closed_at,
                   v.verdict_object AS verdict_object
            FROM trades t
            JOIN verdicts v ON v.id = t.verdict_id
            WHERE t.exit_price IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM outcomes o WHERE o.trade_id = t.id
              )
        """
        cursor: aiosqlite.Cursor = await conn.execute(query)
        rows = await cursor.fetchall()

        for row in rows:
            trade_id: str = str(row[0])
            verdict_id: str = str(row[1])
            ticker: str = str(row[2])
            direction: str = str(row[3])
            entry_price: float = float(row[4])
            exit_price: float = float(row[5])
            closed_at: str = str(row[6]) if row[6] else ""
            verdict_object_raw: str = str(row[7])

            # Find the originating event_id from event_scores -> verdicts link.
            # We pick the first event_score entry whose ticker matches.
            event_cursor: aiosqlite.Cursor = await conn.execute(
                "SELECT event_id FROM event_scores WHERE ticker = ? LIMIT 1",
                (ticker,),
            )
            event_row = await event_cursor.fetchone()
            event_id: str = str(event_row[0]) if event_row else "unknown"

            # Compute forward return
            if entry_price == 0.0:
                forward_return = 0.0
            else:
                forward_return = (exit_price - entry_price) / entry_price

            # Determine directional correctness
            directionally_correct = _is_directionally_correct(direction, forward_return)

            # Determine horizon from verdict_object if available
            horizon = _extract_horizon(verdict_object_raw, closed_at)

            now_iso = datetime.now(tz=UTC).isoformat()

            await conn.execute(
                """
                INSERT INTO outcomes
                    (event_id, verdict_id, trade_id, horizon,
                     forward_return, directionally_correct, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    verdict_id,
                    trade_id,
                    horizon,
                    round(forward_return, 6),
                    1 if directionally_correct else 0,
                    now_iso,
                ),
            )
            written += 1

        if written > 0:
            await conn.commit()

    return written


def _is_directionally_correct(direction: str, forward_return: float) -> bool:
    """Check if the forward return matches the verdict direction.

    LONG  expects a positive return.
    SHORT expects a negative return.
    FLAT  is never directionally correct (ambiguous signal).
    """
    if direction == "long":
        return forward_return > 0.0
    if direction == "short":
        return forward_return < 0.0
    # flat — no directional expectation
    return False


def _extract_horizon(verdict_object_raw: str, closed_at: str) -> str:
    """Extract or infer the trade horizon label.

    If the verdict object contains a ``label`` key we use it;
    otherwise fall back to ``closed_at`` timestamp or ``"unknown"``.
    """
    try:
        obj: dict[str, str] = json.loads(verdict_object_raw)
        label = obj.get("label", "")
        if label:
            return label
    except (json.JSONDecodeError, TypeError):
        pass
    if closed_at:
        return f"closed:{closed_at}"
    return "unknown"
