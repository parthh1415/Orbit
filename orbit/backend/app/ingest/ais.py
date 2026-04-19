"""ORBIT AIS port-snapshot ingestion — polls every 60 s."""

from __future__ import annotations

import json
import logging
import pathlib
import random
from datetime import UTC, datetime

from app.config import Settings
from app.db import get_db
from app.ingest._demo_time import rebase_port_timestamp

logger = logging.getLogger(__name__)

_DEMO_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "demo_snapshot.json"

# Major ports with base ship counts and coordinates.
_PORTS: list[tuple[str, float, float, int]] = [
    ("Singapore", 1.29, 103.85, 340),
    ("Rotterdam", 51.92, 4.48, 185),
    ("Shanghai", 31.23, 121.47, 450),
    ("LA/Long Beach", 33.75, -118.19, 130),
    ("Busan", 35.18, 129.08, 210),
    ("Hsinchu", 24.80, 120.97, 95),
    ("Shenzhen", 22.54, 114.06, 275),
]


def generate_synthetic_snapshots(
    now_iso: str,
) -> list[tuple[str, float, float, int, str]]:
    """Generate synthetic port data for major ports.

    Returns list of (location, lat, lon, ship_count, timestamp).
    """
    rows: list[tuple[str, float, float, int, str]] = []
    for name, lat, lon, base_count in _PORTS:
        jitter = random.randint(-20, 20)
        ship_count = max(0, base_count + jitter)
        rows.append((name, lat, lon, ship_count, now_iso))
    return rows


async def _ingest_demo(settings: Settings) -> int:
    """Load port snapshots from demo_snapshot.json."""
    if not _DEMO_PATH.exists():
        logger.warning("Demo snapshot not found at %s", _DEMO_PATH)
        return 0

    raw = _DEMO_PATH.read_text(encoding="utf-8")
    data: dict[str, object] = json.loads(raw)
    snapshots = data.get("port_snapshots")
    if not isinstance(snapshots, list):
        return 0

    now = datetime.now(tz=UTC)
    recent_ts = rebase_port_timestamp(now)
    rows: list[tuple[str, float, float, int, str]] = []
    for snap in snapshots:
        if not isinstance(snap, dict):
            continue
        rows.append(
            (
                str(snap.get("location", "")),
                float(snap.get("lat", 0.0)),
                float(snap.get("lon", 0.0)),
                int(snap.get("ship_count", 0)),
                recent_ts,
            )
        )

    if not rows:
        return 0

    async with get_db(settings.database_url) as db:
        await db.executemany(
            """INSERT OR REPLACE INTO port_snapshots
               (location, lat, lon, ship_count, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            rows,
        )
        await db.commit()

    return len(rows)


async def poll_ais(settings: Settings) -> int:
    """Poll AIS data (demo or synthetic) and write port snapshots.

    Returns the number of rows written.
    """
    if settings.demo_mode:
        return await _ingest_demo(settings)

    try:
        now_iso = datetime.now(tz=UTC).isoformat()
        rows = generate_synthetic_snapshots(now_iso)

        if not rows:
            return 0

        async with get_db(settings.database_url) as db:
            await db.executemany(
                """INSERT OR REPLACE INTO port_snapshots
                   (location, lat, lon, ship_count, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                rows,
            )
            await db.commit()

        logger.info("AIS: ingested %d port snapshots", len(rows))
        return len(rows)

    except Exception:
        logger.exception("AIS unexpected error")
        return 0
