"""ORBIT FRED macro-data ingestion — daily VIX, 10Y yield, DXY proxy."""

from __future__ import annotations

import hashlib
import json
import logging
import pathlib
from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.db import get_db
from app.ingest._demo_time import rebase_event_timestamp

logger = logging.getLogger(__name__)

_DEMO_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "demo_snapshot.json"

_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# Series we track: (series_id, human label).
_SERIES: list[tuple[str, str]] = [
    ("VIXCLS", "VIX"),
    ("DGS10", "10Y Yield"),
    ("DTWEXBGS", "DXY Proxy"),
]


def make_event_id(series_id: str, date_str: str) -> str:
    """Deterministic event ID for a FRED observation."""
    raw = f"fred-{series_id}-{date_str}"
    return f"fred-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def parse_fred_response(
    series_id: str,
    label: str,
    payload: dict[str, object],
) -> list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]]:
    """Parse FRED JSON into event-table row tuples.

    Returns list of (id, source, timestamp, description, cameo_code,
    goldstein_score, num_sources, lat, lon, countries, sentiment, metadata).
    """
    observations = payload.get("observations")
    if not isinstance(observations, list):
        return []

    rows: list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]] = []
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        date_str = str(obs.get("date", ""))
        value_str = str(obs.get("value", ""))

        # FRED returns "." for missing values.
        if not date_str or value_str == ".":
            continue

        try:
            value = float(value_str)
        except (ValueError, TypeError):
            continue

        ts = f"{date_str}T00:00:00Z"
        row_id = make_event_id(series_id, date_str)
        description = f"{label}: {value}"

        rows.append(
            (
                row_id,
                "fred",
                ts,
                description,
                "",  # cameo_code
                0.0,  # goldstein_score
                1,  # num_sources
                0.0,  # lat
                0.0,  # lon
                "[]",  # countries
                0.0,  # sentiment
                "{}",  # metadata
            )
        )
    return rows


async def _fetch_series(
    client: httpx.AsyncClient,
    series_id: str,
) -> dict[str, object]:
    """Fetch the latest observation for a FRED series."""
    resp = await client.get(
        _BASE_URL,
        params={
            "series_id": series_id,
            "api_key": "DEMO_KEY",
            "file_type": "json",
            "sort_order": "desc",
            "limit": "1",
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    result: dict[str, object] = resp.json()
    return result


async def _ingest_demo(settings: Settings) -> int:
    """Load fred events from demo_snapshot.json."""
    if not _DEMO_PATH.exists():
        logger.warning("Demo snapshot not found at %s", _DEMO_PATH)
        return 0

    raw = _DEMO_PATH.read_text(encoding="utf-8")
    data: dict[str, object] = json.loads(raw)
    events = data.get("events")
    if not isinstance(events, list):
        return 0

    now = datetime.now(tz=UTC)
    rows: list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]] = []
    for evt in events:
        if not isinstance(evt, dict):
            continue
        if str(evt.get("source", "")) != "fred":
            continue
        event_id = str(evt.get("id", ""))
        rows.append(
            (
                event_id,
                str(evt.get("source", "fred")),
                rebase_event_timestamp(event_id, now),
                str(evt.get("description", "")),
                str(evt.get("cameo_code", "")),
                float(evt.get("goldstein_score", 0.0)),
                int(evt.get("num_sources", 1)),
                float(evt.get("lat", 0.0)),
                float(evt.get("lon", 0.0)),
                str(evt.get("countries", "[]")),
                float(evt.get("sentiment", 0.0)),
                str(evt.get("metadata", "{}")),
            )
        )

    if not rows:
        return 0

    async with get_db(settings.database_url) as db:
        await db.executemany(
            """INSERT OR IGNORE INTO events
               (id, source, timestamp, description, cameo_code,
                goldstein_score, num_sources, lat, lon,
                countries, sentiment, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await db.commit()

    return len(rows)


async def poll_fred(settings: Settings) -> int:
    """Poll FRED for macro indicators and write to events table.

    Returns total number of new event rows written.
    """
    if settings.demo_mode:
        return await _ingest_demo(settings)

    total = 0
    try:
        async with httpx.AsyncClient() as client:
            for series_id, label in _SERIES:
                try:
                    payload = await _fetch_series(client, series_id)
                    rows = parse_fred_response(series_id, label, payload)
                    if not rows:
                        continue

                    async with get_db(settings.database_url) as db:
                        await db.executemany(
                            """INSERT OR IGNORE INTO events
                               (id, source, timestamp, description,
                                cameo_code, goldstein_score, num_sources,
                                lat, lon, countries, sentiment, metadata)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            rows,
                        )
                        await db.commit()

                    total += len(rows)
                except httpx.HTTPError as exc:
                    logger.error("FRED HTTP error for %s: %s", series_id, exc)
                except Exception:
                    logger.exception("FRED error for %s", series_id)

    except Exception:
        logger.exception("FRED unexpected error")

    if total:
        logger.info("FRED: ingested %d observations", total)
    return total
