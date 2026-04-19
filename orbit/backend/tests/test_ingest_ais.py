"""Tests for app.ingest.ais — AIS port snapshot ingestion."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.db import get_db, run_migrations
from app.ingest.ais import generate_synthetic_snapshots, poll_ais


def test_generate_synthetic_snapshots_count() -> None:
    """generate_synthetic_snapshots returns 7 port snapshots."""
    now_iso = "2026-04-14T08:00:00Z"
    rows = generate_synthetic_snapshots(now_iso)
    assert len(rows) == 7


def test_generate_synthetic_snapshots_fields() -> None:
    """Each snapshot has (location, lat, lon, ship_count, timestamp)."""
    now_iso = "2026-04-14T08:00:00Z"
    rows = generate_synthetic_snapshots(now_iso)
    for location, lat, lon, ship_count, ts in rows:
        assert isinstance(location, str)
        assert len(location) > 0
        assert isinstance(lat, float)
        assert isinstance(lon, float)
        assert isinstance(ship_count, int)
        assert ship_count >= 0
        assert ts == now_iso


def test_generate_synthetic_snapshots_known_ports() -> None:
    """All seven major ports are present."""
    rows = generate_synthetic_snapshots("2026-04-14T08:00:00Z")
    locations = {r[0] for r in rows}
    assert "Singapore" in locations
    assert "Rotterdam" in locations
    assert "Shanghai" in locations
    assert "LA/Long Beach" in locations
    assert "Busan" in locations
    assert "Hsinchu" in locations
    assert "Shenzhen" in locations


async def test_poll_ais_live_mode(tmp_path: Path) -> None:
    """poll_ais in live mode writes synthetic snapshots to DB."""
    db_path = str(tmp_path / "test.db")
    await run_migrations(db_path)

    settings = Settings(demo_mode=False, database_url=db_path)
    count = await poll_ais(settings)
    assert count == 7

    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM port_snapshots")
        result = await cursor.fetchone()
        assert result is not None
        assert result[0] == 7


async def test_poll_ais_demo_mode(tmp_path: Path) -> None:
    """poll_ais in demo mode reads from demo_snapshot.json."""
    db_path = str(tmp_path / "test.db")
    await run_migrations(db_path)

    # Create a demo snapshot file
    demo_path = tmp_path / "demo_snapshot.json"
    demo_data = {
        "port_snapshots": [
            {
                "location": "TestPort",
                "lat": 1.0,
                "lon": 2.0,
                "ship_count": 42,
                "timestamp": "2026-04-14T08:00:00Z",
            }
        ]
    }
    demo_path.write_text(json.dumps(demo_data), encoding="utf-8")

    import app.ingest.ais as ais_mod

    original_path = ais_mod._DEMO_PATH
    ais_mod._DEMO_PATH = demo_path  # type: ignore[assignment]
    try:
        settings = Settings(demo_mode=True, database_url=db_path)
        count = await poll_ais(settings)
        assert count == 1

        async with get_db(db_path) as db:
            cursor = await db.execute("SELECT location, ship_count FROM port_snapshots")
            rows = await cursor.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "TestPort"
            assert rows[0][1] == 42
    finally:
        ais_mod._DEMO_PATH = original_path  # type: ignore[assignment]
