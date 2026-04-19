"""ORBIT status routes — system health and feed state."""

from __future__ import annotations

from datetime import UTC, datetime

import aiosqlite
from fastapi import APIRouter

from app.db import get_db
from app.schemas import StatusMessage

router = APIRouter(prefix="/api", tags=["status"])


def _format_age(seconds: float) -> str:
    """Format an age in seconds as a compact human-readable string.

    - Under 60 s  -> ``"Xs"``
    - Under 3600 s -> ``"Xm"``
    - 3600 s+      -> ``"Xh"``
    """
    secs = max(0.0, seconds)
    if secs < 60:
        return f"{int(secs)}s"
    if secs < 3600:
        return f"{int(secs // 60)}m"
    return f"{int(secs // 3600)}h"


@router.get("/status", response_model=StatusMessage)
async def get_status() -> StatusMessage:
    """Return current system status including feed health metrics."""
    now = datetime.now(tz=UTC)

    async with get_db() as conn:
        # Last event timestamp
        cursor: aiosqlite.Cursor = await conn.execute("SELECT MAX(timestamp) FROM events")
        row = await cursor.fetchone()
        last_event_ts: str | None = str(row[0]) if row and row[0] else None

        # Count distinct sources as active feeds
        cursor = await conn.execute("SELECT COUNT(DISTINCT source) FROM events")
        row = await cursor.fetchone()
        active_feeds: int = int(row[0]) if row and row[0] else 0

        # Total event count
        cursor = await conn.execute("SELECT COUNT(*) FROM events")
        row = await cursor.fetchone()
        event_count: int = int(row[0]) if row and row[0] else 0

        # Median latency: median age of last 10 events
        cursor = await conn.execute(
            """
            SELECT timestamp FROM events
            ORDER BY timestamp DESC
            LIMIT 10
            """
        )
        recent_rows = await cursor.fetchall()

    # -- compute median age ------------------------------------------------
    median_latency_label: str = "0s"
    if recent_rows:
        ages: list[float] = []
        for r in recent_rows:
            try:
                evt_time = datetime.fromisoformat(str(r[0]))
                if evt_time.tzinfo is None:
                    evt_time = evt_time.replace(tzinfo=UTC)
                age = (now - evt_time).total_seconds()
                ages.append(age)
            except (ValueError, TypeError):
                pass
        if ages:
            sorted_ages = sorted(ages)
            mid = len(sorted_ages) // 2
            median_latency_label = _format_age(sorted_ages[mid])

    # -- compute last-event age --------------------------------------------
    last_label: str = "n/a"
    if last_event_ts is not None:
        try:
            last_dt = datetime.fromisoformat(last_event_ts)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=UTC)
            last_label = f"{_format_age((now - last_dt).total_seconds())} ago"
        except (ValueError, TypeError):
            pass

    feed_status = "active" if active_feeds > 0 else "idle"
    message = (
        f"feeds={feed_status} active_feeds={active_feeds} "
        f"events={event_count} last={last_label} "
        f"latency={median_latency_label}"
    )

    level: str = "info" if active_feeds > 0 else "warn"

    return StatusMessage(
        level=level,
        message=message,
        timestamp=now,
    )
