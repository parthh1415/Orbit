"""ORBIT event routes — scored geopolitical events."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import aiosqlite
from fastapi import APIRouter, HTTPException

from app.config import TRACKED_TICKERS
from app.db import get_db
from app.schemas import DirectionEnum, ScoredEvent

router = APIRouter(prefix="/api/events", tags=["events"])

_EVENTS_COLUMNS = """
    SELECT e.id, e.source, e.timestamp, e.description,
           e.cameo_code, e.goldstein_score, e.num_sources,
           e.lat, e.lon, e.countries, e.sentiment, e.metadata,
           es.ticker, es.relevance, es.implied_direction, es.computed_at"""

_EVENTS_JOIN_SQL = (
    _EVENTS_COLUMNS
    + """
    FROM events e
    JOIN event_scores es ON e.id = es.event_id
"""
)

_EVENTS_LEFT_JOIN_SQL = (
    _EVENTS_COLUMNS
    + """
    FROM events e
    LEFT JOIN event_scores es ON e.id = es.event_id
"""
)

_RECENT_HOURS = 24


def _cutoff_iso() -> str:
    """Return an ISO-8601 timestamp *_RECENT_HOURS* ago (UTC)."""
    return (datetime.now(tz=UTC) - timedelta(hours=_RECENT_HOURS)).isoformat()


def _row_to_scored_event(row: aiosqlite.Row) -> ScoredEvent:
    """Convert a joined events+event_scores row to a ScoredEvent.

    Column order matches ``_EVENTS_JOIN_SQL``:
    0=id, 1=source, 2=timestamp, 3=description, 4=cameo_code,
    5=goldstein_score, 6=num_sources, 7=lat, 8=lon, 9=countries,
    10=sentiment, 11=metadata, 12=ticker, 13=relevance,
    14=implied_direction, 15=computed_at
    """
    countries_raw = str(row[9]) if row[9] else "[]"
    try:
        countries: list[str] = json.loads(countries_raw)
    except (json.JSONDecodeError, TypeError):
        countries = []

    metadata_raw = str(row[11]) if row[11] else "{}"
    try:
        metadata: dict[str, str] = json.loads(metadata_raw)
    except (json.JSONDecodeError, TypeError):
        metadata = {}

    computed_at_raw = row[15]
    computed_at: datetime | None = (
        datetime.fromisoformat(str(computed_at_raw)) if computed_at_raw else None
    )

    return ScoredEvent(
        id=str(row[0]),
        source=str(row[1]),
        timestamp=datetime.fromisoformat(str(row[2])),
        description=str(row[3]),
        cameo_code=str(row[4]) if row[4] else "",
        goldstein_score=round(float(row[5]), 2),
        num_sources=int(row[6]),
        lat=round(float(row[7]), 2),
        lon=round(float(row[8]), 2),
        countries=countries,
        sentiment=round(float(row[10]), 2),
        metadata=metadata,
        ticker=str(row[12]) if row[12] else "",
        relevance=round(float(row[13]), 2) if row[13] else 0.0,
        implied_direction=DirectionEnum(str(row[14])) if row[14] else DirectionEnum.FLAT,
        computed_at=computed_at,
    )


@router.get("/recent", response_model=list[ScoredEvent])
async def get_recent_events() -> list[ScoredEvent]:
    """Return the last 4 high-score events across all tickers (right panel).

    Uses ``event_scores.computed_at`` as the recency filter so that replay
    events whose rebased ``events.timestamp`` has aged out of the window
    still surface when their scores were computed recently.
    """
    cutoff = _cutoff_iso()
    async with get_db() as conn:
        cursor: aiosqlite.Cursor = await conn.execute(
            _EVENTS_JOIN_SQL
            + """
            WHERE es.computed_at >= ?
            ORDER BY es.relevance DESC, e.timestamp DESC
            LIMIT 4
            """,
            (cutoff,),
        )
        rows = await cursor.fetchall()

    return [_row_to_scored_event(r) for r in rows]


@router.get("/{ticker}", response_model=list[ScoredEvent])
async def get_events_for_ticker(ticker: str) -> list[ScoredEvent]:
    """Return last 50 scored events for *ticker* within the recency window."""
    if ticker not in TRACKED_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown ticker '{ticker}'. Must be one of {list(TRACKED_TICKERS)}",
        )

    cutoff = _cutoff_iso()
    async with get_db() as conn:
        cursor: aiosqlite.Cursor = await conn.execute(
            _EVENTS_JOIN_SQL
            + """
            WHERE es.ticker = ?
              AND es.computed_at >= ?
            ORDER BY es.relevance DESC, e.timestamp DESC
            LIMIT 50
            """,
            (ticker, cutoff),
        )
        rows = await cursor.fetchall()

    return [_row_to_scored_event(r) for r in rows]


@router.get("/{event_id}/detail", response_model=ScoredEvent)
async def get_event_detail(event_id: str) -> ScoredEvent:
    """Return a single event with full metadata."""
    async with get_db() as conn:
        cursor: aiosqlite.Cursor = await conn.execute(
            _EVENTS_LEFT_JOIN_SQL + " WHERE e.id = ? LIMIT 1",
            (event_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")

    return _row_to_scored_event(row)
