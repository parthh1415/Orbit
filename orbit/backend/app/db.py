"""Async SQLite connection manager and schema migration for ORBIT."""

from __future__ import annotations

import contextlib
import pathlib
from collections.abc import AsyncIterator

import aiosqlite

from app.config import get_settings

# ---------------------------------------------------------------------------
# SQL — table definitions
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS events (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    description  TEXT NOT NULL,
    cameo_code   TEXT NOT NULL DEFAULT '',
    goldstein_score REAL NOT NULL DEFAULT 0.0,
    num_sources  INTEGER NOT NULL DEFAULT 1,
    lat          REAL NOT NULL DEFAULT 0.0,
    lon          REAL NOT NULL DEFAULT 0.0,
    countries    TEXT NOT NULL DEFAULT '[]',
    sentiment    REAL NOT NULL DEFAULT 0.0,
    metadata     TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS event_scores (
    event_id          TEXT NOT NULL REFERENCES events(id),
    ticker            TEXT NOT NULL,
    relevance         REAL NOT NULL DEFAULT 0.0,
    implied_direction TEXT NOT NULL DEFAULT 'flat',
    computed_at       TEXT,
    PRIMARY KEY (event_id, ticker)
);

CREATE TABLE IF NOT EXISTS verdicts (
    id              TEXT PRIMARY KEY,
    ticker          TEXT NOT NULL,
    verdict_class   TEXT NOT NULL DEFAULT 'hold',
    direction       TEXT NOT NULL DEFAULT 'flat',
    relevance_score REAL NOT NULL DEFAULT 0.0,
    issued_at       TEXT NOT NULL,
    verdict_object  TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS trades (
    id           TEXT PRIMARY KEY,
    verdict_id   TEXT NOT NULL REFERENCES verdicts(id),
    ticker       TEXT NOT NULL,
    direction    TEXT NOT NULL,
    size_shares  INTEGER NOT NULL,
    entry_price  REAL NOT NULL,
    exit_price   REAL,
    executed_at  TEXT NOT NULL,
    closed_at    TEXT,
    realized_pnl REAL
);

CREATE TABLE IF NOT EXISTS outcomes (
    event_id              TEXT NOT NULL REFERENCES events(id),
    verdict_id            TEXT NOT NULL REFERENCES verdicts(id),
    trade_id              TEXT NOT NULL REFERENCES trades(id),
    horizon               TEXT NOT NULL,
    forward_return        REAL NOT NULL,
    directionally_correct INTEGER NOT NULL DEFAULT 0,
    computed_at           TEXT NOT NULL,
    PRIMARY KEY (event_id, verdict_id, trade_id)
);

CREATE TABLE IF NOT EXISTS bars (
    ticker    TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    open      REAL NOT NULL,
    high      REAL NOT NULL,
    low       REAL NOT NULL,
    close     REAL NOT NULL,
    volume    INTEGER NOT NULL,
    PRIMARY KEY (ticker, timestamp)
);

CREATE TABLE IF NOT EXISTS price_cache (
    ticker     TEXT PRIMARY KEY,
    price      REAL NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS port_snapshots (
    location   TEXT NOT NULL,
    lat        REAL NOT NULL,
    lon        REAL NOT NULL,
    ship_count INTEGER NOT NULL,
    timestamp  TEXT NOT NULL,
    PRIMARY KEY (location, timestamp)
);
"""

_INDEX_SQL = """\
CREATE INDEX IF NOT EXISTS idx_events_timestamp
    ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_event_scores_ticker
    ON event_scores(ticker);
CREATE INDEX IF NOT EXISTS idx_verdicts_ticker_issued
    ON verdicts(ticker, issued_at);
CREATE INDEX IF NOT EXISTS idx_trades_ticker
    ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_outcomes_composite
    ON outcomes(event_id, verdict_id, trade_id);
"""

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def _resolve_db_path(url: str | None = None) -> str:
    """Turn the DATABASE_URL setting into an absolute path, creating dirs."""
    raw = url if url is not None else get_settings().database_url
    path = pathlib.Path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


async def get_connection(url: str | None = None) -> aiosqlite.Connection:
    """Open a new async SQLite connection with WAL mode enabled."""
    db_path = _resolve_db_path(url)
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextlib.asynccontextmanager
async def get_db(url: str | None = None) -> AsyncIterator[aiosqlite.Connection]:
    """Async context manager that yields a connection and cleans up."""
    conn = await get_connection(url)
    try:
        yield conn
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


async def run_migrations(url: str | None = None) -> None:
    """Create all tables and indexes if they do not already exist."""
    async with get_db(url) as conn:
        await conn.executescript(_SCHEMA_SQL)
        await conn.executescript(_INDEX_SQL)
        await conn.commit()
