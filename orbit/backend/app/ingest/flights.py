"""ORBIT flight corridor ingestion — synthetic semiconductor supply chain routes."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from app.config import Settings
from app.db import get_db
from app.schemas import FlightRoute

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static route definitions — each (origin, dest, tickers) tuple expands into
# one FlightRoute per ticker so the frontend can filter by relevance_ticker.
# ---------------------------------------------------------------------------

_CORRIDOR_DEFS: list[tuple[str, float, float, str, float, float, str, str, list[str]]] = [
    # (origin, o_lat, o_lon, dest, d_lat, d_lon, cargo, freq, tickers)
    (
        "Taipei",
        25.03,
        121.56,
        "San Jose",
        37.33,
        -121.89,
        "semiconductor",
        "daily",
        ["AAPL", "NVDA", "TSM"],
    ),
    ("Shanghai", 31.23, 121.47, "Rotterdam", 51.92, 4.47, "finished_goods", "weekly", ["AAPL"]),
    (
        "Shenzhen",
        22.54,
        114.06,
        "LA/Long Beach",
        33.77,
        -118.19,
        "components",
        "daily",
        ["AAPL", "NVDA"],
    ),
    (
        "Tokyo",
        35.68,
        139.69,
        "San Francisco",
        37.77,
        -122.42,
        "components",
        "weekly",
        ["NVDA", "TSM"],
    ),
    ("Singapore", 1.35, 103.82, "Busan", 35.18, 129.08, "semiconductor", "weekly", ["TSM"]),
    ("Hsinchu", 24.80, 120.97, "Phoenix", 33.45, -112.07, "semiconductor", "daily", ["TSM"]),
    ("Seoul", 37.57, 126.98, "Austin", 30.27, -97.74, "components", "weekly", ["NVDA"]),
    ("Penang", 5.41, 100.33, "Taipei", 25.03, 121.56, "components", "daily", ["AAPL", "TSM"]),
]


def _build_routes() -> list[FlightRoute]:
    """Expand corridor definitions into one FlightRoute per ticker."""
    routes: list[FlightRoute] = []
    for origin, o_lat, o_lon, dest, d_lat, d_lon, cargo, freq, tickers in _CORRIDOR_DEFS:
        for ticker in tickers:
            route_id = f"{origin}-{dest}-{ticker}".lower().replace(" ", "-").replace("/", "-")
            routes.append(
                FlightRoute(
                    id=route_id,
                    origin=origin,
                    origin_lat=o_lat,
                    origin_lon=o_lon,
                    destination=dest,
                    dest_lat=d_lat,
                    dest_lon=d_lon,
                    cargo_type=cargo,
                    frequency=freq,
                    relevance_ticker=ticker,
                    active=True,
                )
            )
    return routes


# Module-level cache — routes are static so we build them once.
_ROUTES: list[FlightRoute] = _build_routes()


async def get_flight_routes(settings: Settings) -> list[FlightRoute]:
    """Return all synthetic flight corridors.

    *settings* is accepted for interface consistency with other ingest modules
    but is unused since the data is static.
    """
    _ = settings  # keep linters happy
    return list(_ROUTES)


async def poll_flights(settings: Settings) -> int:
    """Record a flight-poll event in the events table for tracking.

    Returns the number of events written (always 1).
    """
    now_iso = datetime.now(tz=UTC).isoformat()
    event_id = uuid.uuid4().hex

    async with get_db(settings.database_url) as db:
        await db.execute(
            """INSERT OR REPLACE INTO events
               (id, source, timestamp, description)
               VALUES (?, ?, ?, ?)""",
            (
                event_id,
                "flights",
                now_iso,
                f"Flight corridor poll: {len(_ROUTES)} active routes",
            ),
        )
        await db.commit()

    logger.info("Flights: recorded poll event with %d routes", len(_ROUTES))
    return 1
