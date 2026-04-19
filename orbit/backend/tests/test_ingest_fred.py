"""Tests for app.ingest.fred — FRED macro data ingestion."""

from __future__ import annotations

from pathlib import Path

from app.db import get_db, run_migrations
from app.ingest.fred import make_event_id, parse_fred_response


def test_make_event_id_deterministic() -> None:
    """Same inputs produce the same event ID."""
    a = make_event_id("VIXCLS", "2026-04-14")
    b = make_event_id("VIXCLS", "2026-04-14")
    assert a == b
    assert a.startswith("fred-")


def test_make_event_id_different_inputs() -> None:
    """Different series or dates produce different IDs."""
    a = make_event_id("VIXCLS", "2026-04-14")
    b = make_event_id("DGS10", "2026-04-14")
    c = make_event_id("VIXCLS", "2026-04-15")
    assert a != b
    assert a != c


def test_parse_fred_response_basic() -> None:
    """parse_fred_response extracts a valid observation."""
    payload: dict[str, object] = {"observations": [{"date": "2026-04-14", "value": "18.5"}]}
    rows = parse_fred_response("VIXCLS", "VIX", payload)
    assert len(rows) == 1

    row = rows[0]
    assert row[0].startswith("fred-")  # id
    assert row[1] == "fred"  # source
    assert row[2] == "2026-04-14T00:00:00Z"  # timestamp
    assert row[3] == "VIX: 18.5"  # description
    assert row[4] == ""  # cameo_code
    assert row[5] == 0.0  # goldstein_score


def test_parse_fred_response_skips_missing_value() -> None:
    """Observations with '.' value (FRED missing marker) are skipped."""
    payload: dict[str, object] = {"observations": [{"date": "2026-04-14", "value": "."}]}
    rows = parse_fred_response("VIXCLS", "VIX", payload)
    assert rows == []


def test_parse_fred_response_skips_bad_value() -> None:
    """Non-numeric values are skipped."""
    payload: dict[str, object] = {"observations": [{"date": "2026-04-14", "value": "N/A"}]}
    rows = parse_fred_response("VIXCLS", "VIX", payload)
    assert rows == []


def test_parse_fred_response_no_observations() -> None:
    """Missing or non-list observations returns empty."""
    assert parse_fred_response("VIXCLS", "VIX", {}) == []
    assert parse_fred_response("VIXCLS", "VIX", {"observations": "bad"}) == []


def test_parse_fred_response_multiple_observations() -> None:
    """Multiple observations produce multiple rows."""
    payload: dict[str, object] = {
        "observations": [
            {"date": "2026-04-14", "value": "18.5"},
            {"date": "2026-04-13", "value": "19.0"},
        ]
    }
    rows = parse_fred_response("VIXCLS", "VIX", payload)
    assert len(rows) == 2


def test_parse_fred_response_empty_date() -> None:
    """Observations with empty date are skipped."""
    payload: dict[str, object] = {"observations": [{"date": "", "value": "18.5"}]}
    rows = parse_fred_response("VIXCLS", "VIX", payload)
    assert rows == []


async def test_parse_fred_writes_to_db(tmp_path: Path) -> None:
    """Parsed FRED data can be written to the events table."""
    db_path = str(tmp_path / "test.db")
    await run_migrations(db_path)

    payload: dict[str, object] = {"observations": [{"date": "2026-04-14", "value": "18.5"}]}
    rows = parse_fred_response("VIXCLS", "VIX", payload)

    async with get_db(db_path) as db:
        await db.executemany(
            """INSERT OR IGNORE INTO events
               (id, source, timestamp, description,
                cameo_code, goldstein_score, num_sources,
                lat, lon, countries, sentiment, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await db.commit()
        cursor = await db.execute("SELECT description FROM events WHERE source = 'fred'")
        result = await cursor.fetchone()
        assert result is not None
        assert result[0] == "VIX: 18.5"
