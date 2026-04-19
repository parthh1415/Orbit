"""ORBIT port routes — port shipping snapshots for the globe visualization."""

from __future__ import annotations

from datetime import datetime

import aiosqlite
from fastapi import APIRouter

from app.db import get_db
from app.schemas import PortSnapshot

router = APIRouter(prefix="/api/ports", tags=["ports"])


def _row_to_snapshot(row: aiosqlite.Row) -> PortSnapshot:
    """Convert a port_snapshots row to a PortSnapshot model.

    Column order: 0=location, 1=lat, 2=lon, 3=ship_count, 4=timestamp.
    """
    return PortSnapshot(
        location=str(row[0]),
        lat=float(row[1]),
        lon=float(row[2]),
        ship_count=int(row[3]),
        timestamp=datetime.fromisoformat(str(row[4])),
    )


@router.get("", response_model=list[PortSnapshot])
async def get_ports() -> list[PortSnapshot]:
    """Return the latest port snapshot for every tracked port."""
    async with get_db() as conn:
        cursor: aiosqlite.Cursor = await conn.execute(
            """SELECT location, lat, lon, ship_count, timestamp
               FROM port_snapshots
               ORDER BY timestamp DESC"""
        )
        rows = await cursor.fetchall()

    return [_row_to_snapshot(r) for r in rows]
