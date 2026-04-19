"""Tests for all ORBIT route modules and the trade execution endpoint."""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.db import run_migrations
from app.main import app

if TYPE_CHECKING:
    from collections.abc import Iterator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> Iterator[None]:
    """Redirect all DB access to a temporary SQLite file.

    We cannot use ``:memory:`` because each ``aiosqlite.connect(":memory:")``
    creates an independent database.  A temp file ensures every connection
    (including those opened inside route handlers) shares the same state.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    monkeypatch.setattr("app.db._resolve_db_path", lambda url: db_path)
    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: _make_test_settings(db_path),
    )

    # Run migrations synchronously
    loop = asyncio.new_event_loop()
    loop.run_until_complete(run_migrations(db_path))
    loop.close()

    yield

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)
    # Also clean WAL/SHM files
    for ext in (".db-wal", ".db-shm"):
        p = db_path.replace(".db", ext) if db_path.endswith(".db") else db_path + ext
        if os.path.exists(p):
            os.unlink(p)


def _make_test_settings(db_path: str) -> object:
    """Return a minimal Settings with the given database path."""
    from app.config import Settings

    return Settings(database_url=db_path)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Provide a synchronous test client."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper: seed data
# ---------------------------------------------------------------------------


def _seed_bars(client: TestClient) -> None:
    """Insert a few bars for AAPL into the test DB."""
    import asyncio

    from app.db import get_db

    async def _insert() -> None:
        async with get_db() as conn:
            for i in range(3):
                ts = f"2025-01-01T10:{i:02d}:00+00:00"
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO bars
                        (ticker, timestamp, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("AAPL", ts, 150.0 + i, 151.0 + i, 149.0 + i, 150.5 + i, 1000 + i),
                )
            await conn.commit()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_insert())
    loop.close()


def _seed_events(client: TestClient) -> str:
    """Insert a scored event and return the event_id."""
    import asyncio

    from app.db import get_db

    event_id = uuid.uuid4().hex

    async def _insert() -> None:
        async with get_db() as conn:
            now = datetime.now(tz=UTC).isoformat()
            await conn.execute(
                """
                INSERT INTO events
                    (id, source, timestamp, description, cameo_code,
                     goldstein_score, num_sources, lat, lon, countries,
                     sentiment, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    "gdelt",
                    now,
                    "Test event description",
                    "042",
                    -5.0,
                    3,
                    25.0,
                    121.0,
                    '["TW"]',
                    -0.3,
                    "{}",
                ),
            )
            await conn.execute(
                """
                INSERT INTO event_scores
                    (event_id, ticker, relevance, implied_direction, computed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, "AAPL", 0.75, "short", now),
            )
            await conn.commit()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_insert())
    loop.close()
    return event_id


def _seed_trade(client: TestClient) -> str:
    """Insert an open trade and return the trade_id."""
    import asyncio

    from app.db import get_db

    trade_id = uuid.uuid4().hex
    verdict_id = uuid.uuid4().hex

    async def _insert() -> None:
        async with get_db() as conn:
            now = datetime.now(tz=UTC).isoformat()
            await conn.execute(
                """
                INSERT INTO verdicts
                    (id, ticker, verdict_class, direction,
                     relevance_score, issued_at, verdict_object)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (verdict_id, "AAPL", "buy", "long", 0.7, now, "{}"),
            )
            await conn.execute(
                """
                INSERT INTO trades
                    (id, verdict_id, ticker, direction,
                     size_shares, entry_price, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (trade_id, verdict_id, "AAPL", "long", 10, 150.50, now),
            )
            await conn.commit()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_insert())
    loop.close()
    return trade_id


def _seed_price_cache(client: TestClient, ticker: str, price: float) -> None:
    """Insert or update a price_cache entry for the given ticker."""
    import asyncio

    from app.db import get_db

    async def _insert() -> None:
        async with get_db() as conn:
            now = datetime.now(tz=UTC).isoformat()
            await conn.execute(
                """
                INSERT INTO price_cache (ticker, price, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE
                SET price = excluded.price, updated_at = excluded.updated_at
                """,
                (ticker, price, now),
            )
            await conn.commit()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_insert())
    loop.close()


def _seed_short_trade(
    client: TestClient, ticker: str, entry_price: float, size_shares: int
) -> str:
    """Insert an open short trade and return the trade_id."""
    import asyncio

    from app.db import get_db

    trade_id = uuid.uuid4().hex
    verdict_id = uuid.uuid4().hex

    async def _insert() -> None:
        async with get_db() as conn:
            now = datetime.now(tz=UTC).isoformat()
            await conn.execute(
                """
                INSERT INTO verdicts
                    (id, ticker, verdict_class, direction,
                     relevance_score, issued_at, verdict_object)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (verdict_id, ticker, "sell", "short", 0.7, now, "{}"),
            )
            await conn.execute(
                """
                INSERT INTO trades
                    (id, verdict_id, ticker, direction,
                     size_shares, entry_price, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (trade_id, verdict_id, ticker, "short", size_shares, entry_price, now),
            )
            await conn.commit()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_insert())
    loop.close()
    return trade_id


def _seed_closed_trade(client: TestClient) -> str:
    """Insert a closed trade with realized_pnl and return the trade_id."""
    import asyncio

    from app.db import get_db

    trade_id = uuid.uuid4().hex
    verdict_id = uuid.uuid4().hex

    async def _insert() -> None:
        async with get_db() as conn:
            now = datetime.now(tz=UTC).isoformat()
            await conn.execute(
                """
                INSERT INTO verdicts
                    (id, ticker, verdict_class, direction,
                     relevance_score, issued_at, verdict_object)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (verdict_id, "AAPL", "buy", "long", 0.7, now, "{}"),
            )
            await conn.execute(
                """
                INSERT INTO trades
                    (id, verdict_id, ticker, direction,
                     size_shares, entry_price, exit_price,
                     executed_at, closed_at, realized_pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    verdict_id,
                    "AAPL",
                    "long",
                    10,
                    150.0,
                    155.0,
                    now,
                    now,
                    50.0,
                ),
            )
            await conn.commit()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_insert())
    loop.close()
    return trade_id


# ---------------------------------------------------------------------------
# 1. Chart routes
# ---------------------------------------------------------------------------


class TestChartRoutes:
    """Tests for GET /api/bars/{ticker}."""

    def test_get_bars_valid_ticker(self, client: TestClient) -> None:
        _seed_bars(client)
        resp = client.get("/api/bars/AAPL")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 3
        bar = data[0]
        assert "ticker" in bar
        assert "timestamp" in bar
        assert "open" in bar
        assert "close" in bar
        assert "volume" in bar
        assert bar["ticker"] == "AAPL"

    def test_get_bars_invalid_ticker(self, client: TestClient) -> None:
        resp = client.get("/api/bars/INVALID")
        assert resp.status_code == 400

    def test_get_bars_empty(self, client: TestClient) -> None:
        resp = client.get("/api/bars/NVDA")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_bars_with_limit(self, client: TestClient) -> None:
        _seed_bars(client)
        resp = client.get("/api/bars/AAPL?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# 2. Portfolio routes
# ---------------------------------------------------------------------------


class TestPortfolioRoutes:
    """Tests for /api/portfolio/ endpoints."""

    def test_positions_empty(self, client: TestClient) -> None:
        resp = client.get("/api/portfolio/positions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_positions_with_trade(self, client: TestClient) -> None:
        _seed_bars(client)
        _seed_trade(client)
        resp = client.get("/api/portfolio/positions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        pos = data[0]
        assert pos["ticker"] == "AAPL"
        assert pos["direction"] == "long"
        assert pos["size_shares"] == 10
        assert "unrealized_pnl" in pos

    def test_positions_unrealized_pnl_uses_latest_bar(self, client: TestClient) -> None:
        """unrealized_pnl must reflect the latest bar close, not entry price."""
        _seed_bars(client)  # last bar close = 152.5 (150.5 + 2)
        _seed_trade(client)  # entry_price = 150.50, size=10, long
        resp = client.get("/api/portfolio/positions")
        assert resp.status_code == 200
        pos = resp.json()[0]
        # current_price should be the latest bar close (152.5)
        assert pos["current_price"] == 152.5
        # unrealized = (152.5 - 150.5) * 10 = 20.0
        assert pos["unrealized_pnl"] == 20.0

    def test_summary_empty(self, client: TestClient) -> None:
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["capital_total"] == 100_000.0
        assert data["capital_deployed"] == 0.0
        assert data["capital_available"] == 100_000.0
        assert data["realized_pnl"] == 0.0
        assert data["unrealized_pnl"] == 0.0
        assert data["total_pnl"] == 0.0
        assert data["open_positions"] == 0
        assert data["closed_positions"] == 0

    def test_summary_with_trade(self, client: TestClient) -> None:
        _seed_bars(client)
        _seed_trade(client)
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["capital_total"] == 100_000.0
        assert data["open_positions"] == 1
        assert data["closed_positions"] == 0
        # capital_deployed = 150.50 * 10 = 1505.0
        assert data["capital_deployed"] == 1505.0
        assert data["capital_available"] == 100_000.0 - 1505.0
        # unrealized = (152.5 - 150.5) * 10 = 20.0
        assert data["unrealized_pnl"] == 20.0
        assert data["realized_pnl"] == 0.0
        assert data["total_pnl"] == 20.0

    def test_summary_with_closed_trade(self, client: TestClient) -> None:
        """Closed trades contribute to realized_pnl and closed_positions."""
        _seed_closed_trade(client)
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["closed_positions"] == 1
        assert data["open_positions"] == 0
        assert data["capital_deployed"] == 0.0
        assert data["capital_available"] == 100_000.0
        assert data["realized_pnl"] == 50.0
        assert data["total_pnl"] == 50.0

    def test_positions_no_bars_fallback_to_entry_price(self, client: TestClient) -> None:
        """Without bars or price_cache, current_price == entry_price, pnl == 0."""
        _seed_trade(client)  # entry_price = 150.50, no bars seeded
        resp = client.get("/api/portfolio/positions")
        assert resp.status_code == 200
        pos = resp.json()[0]
        assert pos["current_price"] == 150.5
        assert pos["unrealized_pnl"] == 0.0

    def test_positions_price_cache_takes_priority(self, client: TestClient) -> None:
        """price_cache should override stale bar data."""
        _seed_bars(client)  # latest bar close = 152.5
        _seed_trade(client)  # entry_price = 150.50, long, size=10
        _seed_price_cache(client, "AAPL", 155.0)  # price_cache says 155.0
        resp = client.get("/api/portfolio/positions")
        assert resp.status_code == 200
        pos = resp.json()[0]
        assert pos["current_price"] == 155.0
        # unrealized = (155.0 - 150.5) * 10 = 45.0
        assert pos["unrealized_pnl"] == 45.0

    def test_positions_short_direction_pnl(self, client: TestClient) -> None:
        """SHORT position: pnl = (entry - current) * size."""
        _seed_short_trade(client, "NVDA", 200.0, 10)
        _seed_price_cache(client, "NVDA", 190.0)
        resp = client.get("/api/portfolio/positions")
        assert resp.status_code == 200
        pos = resp.json()[0]
        assert pos["direction"] == "short"
        assert pos["current_price"] == 190.0
        # unrealized = (200.0 - 190.0) * 10 = 100.0
        assert pos["unrealized_pnl"] == 100.0

    def test_summary_no_bars_unrealized_zero(self, client: TestClient) -> None:
        """Without bars, unrealized_pnl should be 0 (fallback to entry_price)."""
        _seed_trade(client)  # entry_price = 150.50, no bars
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["unrealized_pnl"] == 0.0
        assert data["capital_deployed"] == 1505.0

    def test_summary_price_cache_priority(self, client: TestClient) -> None:
        """Summary unrealized_pnl should use price_cache over bars."""
        _seed_bars(client)  # latest bar close = 152.5
        _seed_trade(client)  # entry_price = 150.50, long, size=10
        _seed_price_cache(client, "AAPL", 155.0)
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        # unrealized = (155.0 - 150.5) * 10 = 45.0
        assert data["unrealized_pnl"] == 45.0
        assert data["total_pnl"] == 45.0


# ---------------------------------------------------------------------------
# 3. Events routes
# ---------------------------------------------------------------------------


class TestEventsRoutes:
    """Tests for /api/events/ endpoints."""

    def test_events_for_ticker(self, client: TestClient) -> None:
        _seed_events(client)
        resp = client.get("/api/events/AAPL")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        evt = data[0]
        assert evt["ticker"] == "AAPL"
        assert "relevance" in evt
        assert "description" in evt

    def test_events_invalid_ticker(self, client: TestClient) -> None:
        resp = client.get("/api/events/INVALID")
        assert resp.status_code == 400

    def test_recent_events_empty(self, client: TestClient) -> None:
        resp = client.get("/api/events/recent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_recent_events_with_data(self, client: TestClient) -> None:
        _seed_events(client)
        resp = client.get("/api/events/recent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_event_detail(self, client: TestClient) -> None:
        event_id = _seed_events(client)
        resp = client.get(f"/api/events/{event_id}/detail")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == event_id

    def test_event_detail_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/events/nonexistent/detail")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Verdict routes
# ---------------------------------------------------------------------------


class TestVerdictRoutes:
    """Tests for GET /api/verdict/{ticker}."""

    def test_verdict_valid_ticker(self, client: TestClient) -> None:
        _seed_events(client)
        resp = client.get("/api/verdict/AAPL")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert "verdict_class" in data
        assert "direction" in data
        assert "relevance_score" in data
        assert "issued_at" in data
        vo = data["verdict_object"]
        assert "top_event" in vo
        assert "top_score" in vo
        assert "exposure_code" in vo
        assert "exposure_weight" in vo
        assert "n_analogs" in vo
        assert "hit_rate" in vo

    def test_verdict_invalid_ticker(self, client: TestClient) -> None:
        resp = client.get("/api/verdict/INVALID")
        assert resp.status_code == 400

    def test_verdict_no_events(self, client: TestClient) -> None:
        resp = client.get("/api/verdict/NVDA")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "NVDA"
        assert data["verdict_class"] == "hold"

    def test_verdict_rewrites_bad_gdelt_description(self, client: TestClient) -> None:
        """A raw GDELT event ID description is replaced with a readable one."""
        import asyncio

        from app.db import get_db

        event_id = uuid.uuid4().hex

        async def _insert() -> None:
            async with get_db() as conn:
                now = datetime.now(tz=UTC).isoformat()
                await conn.execute(
                    """INSERT INTO events
                       (id, source, timestamp, description, cameo_code,
                        goldstein_score, num_sources, lat, lon, countries,
                        sentiment, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id,
                        "gdelt",
                        now,
                        "GDELT event 1299506043",  # bad description
                        "172",  # CAMEO: impose sanctions
                        -7.0,
                        5,
                        25.0,
                        121.0,
                        '["TW", "US"]',
                        -0.5,
                        "{}",
                    ),
                )
                await conn.execute(
                    """INSERT INTO event_scores
                       (event_id, ticker, relevance, implied_direction, computed_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (event_id, "AAPL", 0.80, "short", now),
                )
                await conn.commit()

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_insert())
        loop.close()

        resp = client.get("/api/verdict/AAPL")
        assert resp.status_code == 200
        vo = resp.json()["verdict_object"]
        top_event = vo["top_event"]
        # Should NOT contain the raw GDELT event ID
        assert "GDELT event" not in top_event
        assert "1299506043" not in top_event
        # Should contain a CAMEO-derived verb
        assert "imposed sanctions on" in top_event

    def test_verdict_rewrites_url_description(self, client: TestClient) -> None:
        """A URL description is replaced with a readable one."""
        import asyncio

        from app.db import get_db

        event_id = uuid.uuid4().hex

        async def _insert() -> None:
            async with get_db() as conn:
                now = datetime.now(tz=UTC).isoformat()
                await conn.execute(
                    """INSERT INTO events
                       (id, source, timestamp, description, cameo_code,
                        goldstein_score, num_sources, lat, lon, countries,
                        sentiment, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id,
                        "gdelt",
                        now,
                        "https://example.com/some-article",  # bad: URL as description
                        "042",  # CAMEO: consult
                        -3.0,
                        3,
                        25.0,
                        121.0,
                        '["TW"]',
                        -0.2,
                        "{}",
                    ),
                )
                await conn.execute(
                    """INSERT INTO event_scores
                       (event_id, ticker, relevance, implied_direction, computed_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (event_id, "AAPL", 0.70, "short", now),
                )
                await conn.commit()

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_insert())
        loop.close()

        resp = client.get("/api/verdict/AAPL")
        assert resp.status_code == 200
        vo = resp.json()["verdict_object"]
        top_event = vo["top_event"]
        # Should NOT be a raw URL
        assert not top_event.startswith("https://")
        # Should contain a CAMEO-derived verb
        assert "consulted with" in top_event


# ---------------------------------------------------------------------------
# 5. Scorecard routes
# ---------------------------------------------------------------------------


class TestScorecardRoutes:
    """Tests for /api/scorecard/ endpoints."""

    def test_backtest(self, client: TestClient) -> None:
        resp = client.get("/api/scorecard/backtest")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 3
        row = data[0]
        assert "ticker" in row
        assert "total_trades" in row
        assert "win_rate" in row
        assert "sharpe" in row

    def test_live_scorecard_empty(self, client: TestClient) -> None:
        resp = client.get("/api/scorecard/live")
        assert resp.status_code == 200
        data = resp.json()
        # Always returns one row per tracked ticker, even with no outcomes
        assert len(data) == 3
        tickers = [r["ticker"] for r in data]
        assert tickers == ["AAPL", "NVDA", "TSM"]
        for row in data:
            assert row["total_trades"] == 0
            assert row["wins"] == 0
            assert row["losses"] == 0
            assert row["win_rate"] == 0.0
            assert row["avg_return"] == 0.0
            assert row["sharpe"] == 0.0
            # Wilson CI fields are present
            assert "wilson_center" in row
            assert "wilson_lower" in row
            assert "wilson_upper" in row
            assert "wilson_n" in row


# ---------------------------------------------------------------------------
# 6. Command routes
# ---------------------------------------------------------------------------


class TestCommandRoutes:
    """Tests for POST /api/command/parse."""

    def test_focus_colon(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "focus:AAPL"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["output"] == "FOCUSED ON AAPL"

    def test_focus_space(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "focus AAPL"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["output"] == "FOCUSED ON AAPL"

    def test_focus_case_insensitive(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "FOCUS nvda"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["output"] == "FOCUSED ON NVDA"

    def test_filter_colon(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "filter:TW"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "FILTERED EVENTS TO TW" in data["output"]
        assert "3 MATCHES" in data["output"]

    def test_filter_space(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "filter US"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "US" in data["output"]

    def test_status_command(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "status"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "ALL FEEDS ACTIVE" in data["output"]

    def test_ports_command(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "ports"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "5 PORTS TRACKED" in data["output"]
        assert "SINGAPORE" in data["output"]

    def test_flights_command(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "flights"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "13 CORRIDORS ACTIVE" in data["output"]

    def test_help_command(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "help"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "COMMANDS:" in data["output"]
        assert "FOCUS" in data["output"]

    def test_empty_command(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "UNKNOWN COMMAND" in data["output"]

    def test_unknown_command(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "hello world"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "UNKNOWN COMMAND" in data["output"]

    def test_whitespace_stripped(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "  status  "})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "ALL FEEDS ACTIVE" in data["output"]

    def test_case_insensitive_status(self, client: TestClient) -> None:
        resp = client.post("/api/command/parse", json={"command": "STATUS"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ---------------------------------------------------------------------------
# 7. Status routes
# ---------------------------------------------------------------------------


class TestStatusRoutes:
    """Tests for GET /api/status."""

    def test_status_idle(self, client: TestClient) -> None:
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "level" in data
        assert "message" in data
        assert "timestamp" in data
        assert data["level"] in ("info", "warn")

    def test_status_with_events(self, client: TestClient) -> None:
        _seed_events(client)
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "info"
        assert "active_feeds=1" in data["message"]


# ---------------------------------------------------------------------------
# 8. Trade execution
# ---------------------------------------------------------------------------


class TestTradeExecution:
    """Tests for POST /api/trades/execute."""

    def test_execute_trade(self, client: TestClient) -> None:
        _seed_bars(client)
        resp = client.post(
            "/api/trades/execute",
            json={"ticker": "AAPL", "direction": "long", "size_shares": 1000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "trade_id" in data
        assert len(data["trade_id"]) > 0
        assert "Paper trade executed" in data["message"]

    def test_execute_trade_preserves_size_shares(self, client: TestClient) -> None:
        """size_shares sent by the frontend must appear verbatim in the response."""
        _seed_bars(client)
        resp = client.post(
            "/api/trades/execute",
            json={"ticker": "AAPL", "direction": "short", "size_shares": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "short 10 shares of AAPL" in data["message"]

    def test_execute_trade_invalid_ticker(self, client: TestClient) -> None:
        resp = client.post(
            "/api/trades/execute",
            json={"ticker": "INVALID", "direction": "long", "size_shares": 100},
        )
        assert resp.status_code == 400

    def test_execute_trade_no_bars(self, client: TestClient) -> None:
        resp = client.post(
            "/api/trades/execute",
            json={"ticker": "NVDA", "direction": "long", "size_shares": 100},
        )
        assert resp.status_code == 400
        assert "No bar data" in resp.json()["detail"]

    def test_zero_share_trades_excluded_from_positions(self, client: TestClient) -> None:
        """Ghost trades with size_shares=0 must not appear in portfolio positions."""
        import asyncio

        from app.db import get_db

        async def _insert_ghost() -> None:
            async with get_db() as conn:
                now = datetime.now(tz=UTC).isoformat()
                vid = uuid.uuid4().hex
                await conn.execute(
                    """INSERT INTO verdicts (id, ticker, verdict_class, direction,
                       relevance_score, issued_at, verdict_object)
                       VALUES (?, ?, 'hold', 'long', 0.0, ?, '{}')""",
                    (vid, "AAPL", now),
                )
                await conn.execute(
                    """INSERT INTO trades (id, verdict_id, ticker, direction,
                       size_shares, entry_price, executed_at)
                       VALUES (?, ?, ?, ?, 0, 150.0, ?)""",
                    (uuid.uuid4().hex, vid, "AAPL", "long", now),
                )
                await conn.commit()

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_insert_ghost())
        loop.close()

        resp = client.get("/api/portfolio/positions")
        assert resp.status_code == 200
        assert resp.json() == []
