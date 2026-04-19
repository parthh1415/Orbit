"""Tests for app.db — async SQLite connection manager and migrations."""

from __future__ import annotations

import tempfile
from pathlib import Path

import aiosqlite
import pytest

from app.db import get_connection, get_db, run_migrations


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """Return a temporary database file path."""
    return str(tmp_path / "test_orbit.db")


async def test_run_migrations_creates_tables(tmp_db_path: str) -> None:
    """After run_migrations, all seven tables exist."""
    await run_migrations(tmp_db_path)

    async with aiosqlite.connect(tmp_db_path) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        table_names = sorted(r[0] for r in rows)

    expected = sorted(
        [
            "bars",
            "event_scores",
            "events",
            "outcomes",
            "port_snapshots",
            "price_cache",
            "trades",
            "verdicts",
        ]
    )
    assert table_names == expected


async def test_run_migrations_creates_indexes(tmp_db_path: str) -> None:
    """After run_migrations, the expected indexes exist."""
    await run_migrations(tmp_db_path)

    async with aiosqlite.connect(tmp_db_path) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        rows = await cursor.fetchall()
        index_names = sorted(r[0] for r in rows)

    expected = sorted(
        [
            "idx_events_timestamp",
            "idx_event_scores_ticker",
            "idx_verdicts_ticker_issued",
            "idx_trades_ticker",
            "idx_outcomes_composite",
        ]
    )
    assert index_names == expected


async def test_run_migrations_idempotent(tmp_db_path: str) -> None:
    """Calling run_migrations twice does not raise."""
    await run_migrations(tmp_db_path)
    await run_migrations(tmp_db_path)  # should not raise


async def test_get_connection_returns_connection(tmp_db_path: str) -> None:
    """get_connection returns an open aiosqlite connection."""
    conn = await get_connection(tmp_db_path)
    try:
        cursor = await conn.execute("SELECT 1")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 1
    finally:
        await conn.close()


async def test_get_db_context_manager(tmp_db_path: str) -> None:
    """get_db yields a connection and closes it on exit."""
    async with get_db(tmp_db_path) as conn:
        cursor = await conn.execute("SELECT 1")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 1


async def test_wal_mode_enabled(tmp_db_path: str) -> None:
    """WAL journal mode is set on new connections."""
    conn = await get_connection(tmp_db_path)
    try:
        cursor = await conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "wal"
    finally:
        await conn.close()


async def test_foreign_keys_enabled(tmp_db_path: str) -> None:
    """Foreign keys pragma is turned on."""
    conn = await get_connection(tmp_db_path)
    try:
        cursor = await conn.execute("PRAGMA foreign_keys")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 1
    finally:
        await conn.close()


async def test_parent_directory_created() -> None:
    """get_connection creates parent dirs if needed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        nested = str(Path(tmpdir) / "a" / "b" / "test.db")
        conn = await get_connection(nested)
        await conn.close()
        assert Path(nested).parent.is_dir()


async def test_insert_and_read_event(tmp_db_path: str) -> None:
    """Round-trip: insert into events, then read back."""
    await run_migrations(tmp_db_path)

    async with get_db(tmp_db_path) as conn:
        await conn.execute(
            "INSERT INTO events (id, source, timestamp, description) VALUES (?, ?, ?, ?)",
            ("e1", "test", "2025-01-01T00:00:00Z", "Test event"),
        )
        await conn.commit()

        cursor = await conn.execute("SELECT id, description FROM events WHERE id = ?", ("e1",))
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "e1"
        assert row[1] == "Test event"
