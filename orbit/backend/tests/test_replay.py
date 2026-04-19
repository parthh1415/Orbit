"""Tests for the ORBIT historical replay engine.

Covers:
- Timestamp rebasing math (the critical correctness property)
- GDELT country-name to ISO normalization
- Event scoring helper
- GDELT window timestamp generation
- ReplayCache data structure
- Yahoo Finance bar fallback (prefetch + parsing)
- Replay bar insertion into SQLite with rebased timestamps
"""

from __future__ import annotations

import calendar
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import TRACKED_TICKERS
from app.db import get_db, run_migrations
from app.ingest.replay import (
    GDELT_TO_ISO,
    ReplayCache,
    _gdelt_window_timestamps,
    _normalize_countries,
    _prefetch_yahoo,
    _replay_date_to_market_unix,
    _score_event_for_tickers,
    rebase_timestamp,
)

# ===================================================================
# Timestamp rebasing — the critical correctness property
# ===================================================================


class TestRebaseTimestamp:
    """Verify that replay items appear at the correct relative age."""

    def test_event_15_min_ago_in_replay(self) -> None:
        """Item at 9:45 AM, clock at 10:00 AM -> 15 min before real_now."""
        replay_clock = datetime(2026, 4, 16, 14, 0, 0, tzinfo=UTC)  # 10:00 AM ET
        item_ts = datetime(2026, 4, 16, 13, 45, 0, tzinfo=UTC)  # 9:45 AM ET
        real_now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC)  # arbitrary "now"

        rebased = rebase_timestamp(item_ts, replay_clock, real_now)
        rebased_dt = datetime.fromisoformat(rebased)

        expected = real_now - timedelta(minutes=15)
        delta = abs((rebased_dt - expected).total_seconds())
        assert delta < 1.0, f"Expected ~15 min ago, got delta={delta}s"

    def test_event_1_hour_ago_in_replay(self) -> None:
        """Item at 9:00 AM, clock at 10:00 AM -> 1 hour before real_now."""
        replay_clock = datetime(2026, 4, 16, 14, 0, 0, tzinfo=UTC)
        item_ts = datetime(2026, 4, 16, 13, 0, 0, tzinfo=UTC)
        real_now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC)

        rebased = rebase_timestamp(item_ts, replay_clock, real_now)
        rebased_dt = datetime.fromisoformat(rebased)

        expected = real_now - timedelta(hours=1)
        delta = abs((rebased_dt - expected).total_seconds())
        assert delta < 1.0, f"Expected ~1 hour ago, got delta={delta}s"

    def test_event_at_clock_is_now(self) -> None:
        """Item exactly at the replay clock -> rebased to real_now."""
        replay_clock = datetime(2026, 4, 16, 14, 0, 0, tzinfo=UTC)
        item_ts = datetime(2026, 4, 16, 14, 0, 0, tzinfo=UTC)
        real_now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC)

        rebased = rebase_timestamp(item_ts, replay_clock, real_now)
        rebased_dt = datetime.fromisoformat(rebased)

        delta = abs((rebased_dt - real_now).total_seconds())
        assert delta < 1.0

    def test_future_item_clamped_to_now(self) -> None:
        """Item slightly in the future (shouldn't happen) -> clamped to real_now."""
        replay_clock = datetime(2026, 4, 16, 14, 0, 0, tzinfo=UTC)
        item_ts = datetime(2026, 4, 16, 14, 5, 0, tzinfo=UTC)  # 5 min ahead
        real_now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC)

        rebased = rebase_timestamp(item_ts, replay_clock, real_now)
        rebased_dt = datetime.fromisoformat(rebased)

        # Should be clamped to real_now (not in the future)
        delta = abs((rebased_dt - real_now).total_seconds())
        assert delta < 1.0

    def test_recency_decay_with_rebased_timestamp(self) -> None:
        """Rebased timestamps produce correct recency_decay values.

        An event from 1 hour ago in replay should have decay of exp(-1/24) ~= 0.959.
        """
        import math

        from app.scoring.correlation import recency_decay

        replay_clock = datetime(2026, 4, 16, 14, 30, 0, tzinfo=UTC)
        item_ts = datetime(2026, 4, 16, 13, 30, 0, tzinfo=UTC)  # 1 hour ago
        real_now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC)

        rebased = rebase_timestamp(item_ts, replay_clock, real_now)
        rebased_dt = datetime.fromisoformat(rebased)
        if rebased_dt.tzinfo is None:
            rebased_dt = rebased_dt.replace(tzinfo=UTC)

        hours_since = (real_now - rebased_dt).total_seconds() / 3600.0
        decay = recency_decay(hours_since)

        expected_decay = math.exp(-1.0 / 24.0)
        assert abs(decay - expected_decay) < 1e-6, (
            f"Expected decay={expected_decay:.6f}, got {decay:.6f}"
        )

    def test_multiple_events_preserve_ordering(self) -> None:
        """Events at t1 < t2 should have rebased_t1 < rebased_t2."""
        replay_clock = datetime(2026, 4, 16, 15, 0, 0, tzinfo=UTC)
        real_now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=UTC)

        ts_early = datetime(2026, 4, 16, 13, 30, 0, tzinfo=UTC)
        ts_late = datetime(2026, 4, 16, 14, 30, 0, tzinfo=UTC)

        rebased_early = datetime.fromisoformat(rebase_timestamp(ts_early, replay_clock, real_now))
        rebased_late = datetime.fromisoformat(rebase_timestamp(ts_late, replay_clock, real_now))

        assert rebased_early < rebased_late, (
            f"Ordering not preserved: {rebased_early} >= {rebased_late}"
        )


# ===================================================================
# GDELT country normalization
# ===================================================================


class TestNormalizeCountries:
    """Test the GDELT country name -> ISO code mapping."""

    def test_known_countries(self) -> None:
        raw = json.dumps(["UNITED STATES", "CHINA"])
        result = json.loads(_normalize_countries(raw))
        assert "US" in result
        assert "CN" in result

    def test_already_iso(self) -> None:
        """Codes not in the map pass through unchanged."""
        raw = json.dumps(["DE", "FR"])
        result = json.loads(_normalize_countries(raw))
        assert result == ["DE", "FR"]

    def test_mixed(self) -> None:
        raw = json.dumps(["TAIWAN", "JP"])
        result = json.loads(_normalize_countries(raw))
        assert "TW" in result
        assert "JP" in result

    def test_empty_json(self) -> None:
        assert _normalize_countries("[]") == "[]"

    def test_invalid_json(self) -> None:
        assert _normalize_countries("not json") == "[]"

    def test_dedup(self) -> None:
        """USA and UNITED STATES both map to US — should not duplicate."""
        raw = json.dumps(["USA", "UNITED STATES"])
        result = json.loads(_normalize_countries(raw))
        assert result.count("US") == 1

    def test_case_insensitive(self) -> None:
        raw = json.dumps(["china", "Japan"])
        result = json.loads(_normalize_countries(raw))
        assert "CN" in result
        assert "JP" in result

    def test_all_mappings_present(self) -> None:
        """Every value in GDELT_TO_ISO is a 2-letter code."""
        for key, val in GDELT_TO_ISO.items():
            assert len(val) == 2, f"Bad ISO code for {key}: {val}"


# ===================================================================
# Event scoring helper
# ===================================================================


class TestScoreEventForTickers:
    def test_us_event_scores_aapl(self) -> None:
        """A US event with strong goldstein should score positively for AAPL."""
        results = _score_event_for_tickers(
            countries_json=json.dumps(["US"]),
            goldstein_score=-5.0,
            num_sources=10,
        )
        tickers_scored = [r[0] for r in results]
        assert "AAPL" in tickers_scored

    def test_tw_event_scores_tsm(self) -> None:
        """A Taiwan event should score highly for TSM."""
        results = _score_event_for_tickers(
            countries_json=json.dumps(["TW"]),
            goldstein_score=-8.0,
            num_sources=10,
        )
        tsm_scores = [r for r in results if r[0] == "TSM"]
        assert len(tsm_scores) == 1
        assert tsm_scores[0][1] > 0.3  # TSM TW exposure is 0.90

    def test_unknown_country_returns_empty(self) -> None:
        """Country with no exposure mapping -> no scores."""
        results = _score_event_for_tickers(
            countries_json=json.dumps(["XX"]),
            goldstein_score=-5.0,
            num_sources=10,
        )
        assert results == []

    def test_zero_goldstein_returns_empty(self) -> None:
        """Zero goldstein score -> zero relevance -> no results."""
        results = _score_event_for_tickers(
            countries_json=json.dumps(["US"]),
            goldstein_score=0.0,
            num_sources=10,
        )
        assert results == []

    def test_direction_short_for_negative(self) -> None:
        """Negative goldstein -> short direction."""
        results = _score_event_for_tickers(
            countries_json=json.dumps(["US"]),
            goldstein_score=-5.0,
            num_sources=10,
        )
        for _, _, direction in results:
            assert direction == "short"

    def test_direction_long_for_positive(self) -> None:
        """Positive goldstein -> long direction."""
        results = _score_event_for_tickers(
            countries_json=json.dumps(["US"]),
            goldstein_score=5.0,
            num_sources=10,
        )
        for _, _, direction in results:
            assert direction == "long"

    def test_us_tw_event_scores_tsm_above_half(self) -> None:
        """Event with countries=["US","TW"] should score >0.5 for TSM.

        TSM has TW exposure of 0.90.  With goldstein=-10 and 10 sources
        the formula gives 0.90 * 1.0 * 1.0 * 1.0 = 0.90 > 0.5.
        """
        results = _score_event_for_tickers(
            countries_json=json.dumps(["US", "TW"]),
            goldstein_score=-10.0,
            num_sources=10,
        )
        tsm = [r for r in results if r[0] == "TSM"]
        assert len(tsm) == 1, "TSM should be scored"
        assert tsm[0][1] > 0.5, f"TSM relevance {tsm[0][1]} should be > 0.5"

    def test_raw_gdelt_names_normalised_before_scoring(self) -> None:
        """Raw GDELT country names are normalised to ISO codes inside the scorer.

        Passing full names like "UNITED STATES" and "TAIWAN" should
        produce the same scores as passing "US" and "TW".
        """
        raw_results = _score_event_for_tickers(
            countries_json=json.dumps(["UNITED STATES", "TAIWAN"]),
            goldstein_score=-7.0,
            num_sources=5,
        )
        iso_results = _score_event_for_tickers(
            countries_json=json.dumps(["US", "TW"]),
            goldstein_score=-7.0,
            num_sources=5,
        )
        assert len(raw_results) > 0, "Raw names should still produce scores"
        assert len(raw_results) == len(iso_results), "Same number of scored tickers"

        raw_by_ticker = {t: s for t, s, _ in raw_results}
        iso_by_ticker = {t: s for t, s, _ in iso_results}
        for ticker in raw_by_ticker:
            assert abs(raw_by_ticker[ticker] - iso_by_ticker[ticker]) < 1e-9, (
                f"{ticker}: raw={raw_by_ticker[ticker]}, iso={iso_by_ticker[ticker]}"
            )

    def test_three_letter_cameo_codes_normalised(self) -> None:
        """GDELT CAMEO 3-letter codes (USA, CHN, TWN) are normalised to ISO-2."""
        results = _score_event_for_tickers(
            countries_json=json.dumps(["USA", "TWN"]),
            goldstein_score=-10.0,
            num_sources=10,
        )
        tsm = [r for r in results if r[0] == "TSM"]
        assert len(tsm) == 1
        # TWN -> TW -> 0.90 exposure for TSM
        assert tsm[0][1] > 0.5, f"TSM relevance {tsm[0][1]} should be > 0.5"

    def test_case_insensitive_country_normalisation(self) -> None:
        """Lowercase / mixed-case country codes should still match exposure."""
        results = _score_event_for_tickers(
            countries_json=json.dumps(["us", "tw"]),
            goldstein_score=-10.0,
            num_sources=10,
        )
        assert len(results) > 0, "Lowercase codes should still produce scores"
        tsm = [r for r in results if r[0] == "TSM"]
        assert len(tsm) == 1
        assert tsm[0][1] > 0.5


# ===================================================================
# GDELT window timestamps
# ===================================================================


class TestGdeltWindowTimestamps:
    def test_returns_list_of_strings(self) -> None:
        stamps = _gdelt_window_timestamps("2026-04-16")
        assert isinstance(stamps, list)
        assert all(isinstance(s, str) for s in stamps)

    def test_format_is_14_digits(self) -> None:
        stamps = _gdelt_window_timestamps("2026-04-16")
        for s in stamps:
            assert len(s) == 14
            assert s.isdigit()

    def test_covers_trading_hours(self) -> None:
        """Should cover from ~12:30 UTC to ~21:15 UTC."""
        stamps = _gdelt_window_timestamps("2026-04-16")
        assert stamps[0].startswith("20260416123")
        assert any(s.startswith("202604162") for s in stamps)
        assert len(stamps) >= 20  # ~36 windows in 8.75 hours at 15 min each

    def test_15_min_intervals(self) -> None:
        """Consecutive stamps should be 15 minutes apart."""
        stamps = _gdelt_window_timestamps("2026-04-16")
        for i in range(len(stamps) - 1):
            t1 = datetime.strptime(stamps[i], "%Y%m%d%H%M%S")
            t2 = datetime.strptime(stamps[i + 1], "%Y%m%d%H%M%S")
            diff = (t2 - t1).total_seconds()
            assert diff == 900.0, f"Expected 900s gap, got {diff}s"


# ===================================================================
# ReplayCache
# ===================================================================


class TestReplayCache:
    def test_empty_cache(self) -> None:
        cache = ReplayCache()
        assert cache.events == []
        assert cache.bars == []
        assert cache.articles == []
        assert cache.event_timestamps == []
        assert cache.bar_timestamps == []
        assert cache.article_timestamps == []


# ===================================================================
# Integration: DB insertion with rebased timestamps
# ===================================================================


class TestReplayDBIntegration:
    async def test_rebased_events_appear_recent(self, tmp_path: Path) -> None:
        """Events inserted with rebased timestamps should appear within last 24h."""
        db_path = str(tmp_path / "replay_test.db")
        await run_migrations(db_path)

        now = datetime.now(tz=UTC)
        replay_clock = datetime(2026, 4, 16, 15, 0, 0, tzinfo=UTC)
        item_ts = datetime(2026, 4, 16, 14, 30, 0, tzinfo=UTC)  # 30 min ago in replay

        rebased_ts = rebase_timestamp(item_ts, replay_clock, now)

        async with get_db(db_path) as db:
            await db.execute(
                """INSERT INTO events
                   (id, source, timestamp, description, cameo_code,
                    goldstein_score, num_sources, lat, lon,
                    countries, sentiment, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "replay-test-001",
                    "gdelt",
                    rebased_ts,
                    "Test replay event",
                    "042",
                    -3.4,
                    5,
                    39.9,
                    116.4,
                    '["US"]',
                    0.0,
                    "{}",
                ),
            )
            await db.commit()

            # Query events from last 24 hours (same filter as verdict route)
            cutoff = (now - timedelta(hours=24)).isoformat()
            cursor = await db.execute(
                "SELECT id, timestamp FROM events WHERE timestamp >= ?",
                (cutoff,),
            )
            rows = list(await cursor.fetchall())

        assert len(rows) == 1
        assert rows[0][0] == "replay-test-001"

        # Verify the stored timestamp is about 30 min before now
        stored_ts = datetime.fromisoformat(str(rows[0][1]))
        if stored_ts.tzinfo is None:
            stored_ts = stored_ts.replace(tzinfo=UTC)
        age_minutes = (now - stored_ts).total_seconds() / 60.0
        assert 29.0 < age_minutes < 31.0, f"Expected ~30 min age, got {age_minutes:.1f} min"

    async def test_rebased_bars_appear_as_current_price(self, tmp_path: Path) -> None:
        """Bars inserted with rebased timestamps should be queryable for current_price."""
        db_path = str(tmp_path / "bars_test.db")
        await run_migrations(db_path)

        now = datetime.now(tz=UTC)
        replay_clock = datetime(2026, 4, 16, 15, 0, 0, tzinfo=UTC)

        # Two bars: one 30 min ago, one 10 min ago in replay
        bar_30m = datetime(2026, 4, 16, 14, 30, 0, tzinfo=UTC)
        bar_10m = datetime(2026, 4, 16, 14, 50, 0, tzinfo=UTC)

        rebased_30m = rebase_timestamp(bar_30m, replay_clock, now)
        rebased_10m = rebase_timestamp(bar_10m, replay_clock, now)

        async with get_db(db_path) as db:
            await db.executemany(
                """INSERT OR IGNORE INTO bars
                   (ticker, timestamp, open, high, low, close, volume)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    ("AAPL", rebased_30m, 200.0, 201.0, 199.0, 200.5, 1000),
                    ("AAPL", rebased_10m, 201.0, 202.0, 200.0, 201.5, 1500),
                ],
            )
            await db.commit()

            # The positions endpoint query: latest close per ticker
            cursor = await db.execute(
                "SELECT close FROM bars WHERE ticker = ? ORDER BY timestamp DESC LIMIT 1",
                ("AAPL",),
            )
            row = await cursor.fetchone()

        assert row is not None
        assert float(row[0]) == 201.5  # The more recent bar's close


# ===================================================================
# Yahoo Finance fallback — Unix timestamp computation
# ===================================================================


class TestReplayDateToMarketUnix:
    """Verify that _replay_date_to_market_unix produces correct UNIX timestamps."""

    def test_april_16_2026_market_hours(self) -> None:
        """April 16, 2026: market open 13:30 UTC, close 21:00 UTC."""
        period1, period2 = _replay_date_to_market_unix("2026-04-16")

        open_dt = datetime(2026, 4, 16, 13, 30, 0, tzinfo=UTC)
        close_dt = datetime(2026, 4, 16, 21, 0, 0, tzinfo=UTC)

        assert period1 == int(calendar.timegm(open_dt.timetuple()))
        assert period2 == int(calendar.timegm(close_dt.timetuple()))

    def test_period2_after_period1(self) -> None:
        period1, period2 = _replay_date_to_market_unix("2026-04-16")
        assert period2 > period1
        # Should be 7.5 hours = 27000 seconds apart
        assert period2 - period1 == 27000


# ===================================================================
# Yahoo Finance fallback — response parsing
# ===================================================================


def _make_yahoo_response(
    ticker: str,
    timestamps: list[int],
    opens: list[float | None],
    highs: list[float | None],
    lows: list[float | None],
    closes: list[float | None],
    volumes: list[int | None],
) -> dict[str, object]:
    """Build a mock Yahoo Finance chart response."""
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": opens,
                                "high": highs,
                                "low": lows,
                                "close": closes,
                                "volume": volumes,
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


class TestPrefetchYahoo:
    """Test _prefetch_yahoo with mocked HTTP responses."""

    async def test_parses_valid_response(self) -> None:
        """Bars from a valid Yahoo response are parsed into the correct format."""
        ts1 = 1744807800  # 2026-04-16 13:30:00 UTC
        ts2 = 1744807860  # 2026-04-16 13:31:00 UTC

        responses: dict[str, dict[str, object]] = {}
        for ticker in TRACKED_TICKERS:
            responses[ticker] = _make_yahoo_response(
                ticker=ticker,
                timestamps=[ts1, ts2],
                opens=[150.0, 150.5],
                highs=[151.0, 151.5],
                lows=[149.0, 149.5],
                closes=[150.5, 151.0],
                volumes=[10000, 12000],
            )

        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            for ticker in TRACKED_TICKERS:
                if ticker in url:
                    return httpx.Response(
                        200,
                        json=responses[ticker],
                        request=httpx.Request("GET", url),
                    )
            return httpx.Response(404, request=httpx.Request("GET", url))

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = mock_get

        rows, timestamps = await _prefetch_yahoo(client, "2026-04-16")

        # 2 bars per ticker x 3 tickers = 6
        assert len(rows) == len(TRACKED_TICKERS) * 2
        assert len(timestamps) == len(rows)

        # Check row format: (ticker, iso_timestamp, open, high, low, close, volume)
        first_row = rows[0]
        assert len(first_row) == 7
        assert isinstance(first_row[0], str)  # ticker
        assert isinstance(first_row[1], str)  # ISO timestamp
        assert isinstance(first_row[2], float)  # open
        assert isinstance(first_row[6], int)  # volume

    async def test_skips_none_bars(self) -> None:
        """Bars with None values (outside market hours) are skipped."""
        ts1 = 1744807800
        ts2 = 1744807860

        responses: dict[str, dict[str, object]] = {}
        for ticker in TRACKED_TICKERS:
            responses[ticker] = _make_yahoo_response(
                ticker=ticker,
                timestamps=[ts1, ts2],
                opens=[150.0, None],
                highs=[151.0, None],
                lows=[149.0, None],
                closes=[150.5, None],
                volumes=[10000, None],
            )

        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            for ticker in TRACKED_TICKERS:
                if ticker in url:
                    return httpx.Response(
                        200,
                        json=responses[ticker],
                        request=httpx.Request("GET", url),
                    )
            return httpx.Response(404, request=httpx.Request("GET", url))

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = mock_get

        rows, _timestamps = await _prefetch_yahoo(client, "2026-04-16")

        # Only 1 valid bar per ticker (the second has None values)
        assert len(rows) == len(TRACKED_TICKERS)

    async def test_handles_http_error(self) -> None:
        """HTTP errors for individual tickers are logged and skipped."""

        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            raise httpx.HTTPStatusError(
                "Server error",
                request=httpx.Request("GET", url),
                response=httpx.Response(500),
            )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = mock_get

        rows, timestamps = await _prefetch_yahoo(client, "2026-04-16")

        assert rows == []
        assert timestamps == []

    async def test_handles_malformed_json(self) -> None:
        """Malformed JSON responses are handled gracefully."""

        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(
                200,
                json={"chart": {"result": []}},
                request=httpx.Request("GET", url),
            )

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = mock_get

        rows, _timestamps = await _prefetch_yahoo(client, "2026-04-16")
        assert rows == []

    async def test_bars_sorted_by_timestamp(self) -> None:
        """Bars across tickers are sorted chronologically."""
        ts1 = 1744807800
        ts2 = 1744807860

        responses: dict[str, dict[str, object]] = {}
        for ticker in TRACKED_TICKERS:
            responses[ticker] = _make_yahoo_response(
                ticker=ticker,
                timestamps=[ts1, ts2],
                opens=[150.0, 150.5],
                highs=[151.0, 151.5],
                lows=[149.0, 149.5],
                closes=[150.5, 151.0],
                volumes=[10000, 12000],
            )

        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            for ticker in TRACKED_TICKERS:
                if ticker in url:
                    return httpx.Response(
                        200,
                        json=responses[ticker],
                        request=httpx.Request("GET", url),
                    )
            return httpx.Response(404, request=httpx.Request("GET", url))

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = mock_get

        _rows, timestamps = await _prefetch_yahoo(client, "2026-04-16")

        # Timestamps should be in non-decreasing order
        for i in range(len(timestamps) - 1):
            assert timestamps[i] <= timestamps[i + 1], (
                f"Not sorted at index {i}: {timestamps[i]} > {timestamps[i + 1]}"
            )


# ===================================================================
# Integration: Yahoo fallback in prefetch_replay_data
# ===================================================================


class TestPrefetchFallbackIntegration:
    """Verify that prefetch_replay_data falls back to Yahoo when Alpaca is empty."""

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
    async def test_yahoo_fallback_populates_cache(self) -> None:
        """When Alpaca returns 0 bars, Yahoo Finance fills the cache."""
        from app.config import Settings
        from app.ingest.replay import prefetch_replay_data

        settings = Settings(
            replay_mode=True,
            replay_date="2026-04-16",
            replay_speed=60,
        )

        ts1 = 1744807800

        yahoo_resp: dict[str, object] = _make_yahoo_response(
            ticker="AAPL",
            timestamps=[ts1],
            opens=[150.0],
            highs=[151.0],
            lows=[149.0],
            closes=[150.5],
            volumes=[10000],
        )

        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            # GDELT and NewsAPI: return empty
            if "gdelt" in url.lower():
                return httpx.Response(404, request=httpx.Request("GET", url))
            if "newsapi" in url.lower():
                return httpx.Response(
                    200,
                    json={"articles": []},
                    request=httpx.Request("GET", url),
                )
            # Alpaca: return no bars (simulating weekend failure)
            if "alpaca" in url.lower():
                return httpx.Response(
                    200,
                    json={"bars": []},
                    request=httpx.Request("GET", url),
                )
            # Yahoo Finance: return valid bars
            if "yahoo" in url.lower():
                return httpx.Response(
                    200,
                    json=yahoo_resp,
                    request=httpx.Request("GET", url),
                )
            return httpx.Response(404, request=httpx.Request("GET", url))

        mock_client = AsyncMock()
        mock_client.get = mock_get

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.ingest.replay.httpx.AsyncClient", return_value=mock_ctx):
            cache = await prefetch_replay_data(settings)

        # Yahoo should have provided bars for all tracked tickers
        assert len(cache.bars) > 0
        assert len(cache.bar_timestamps) == len(cache.bars)
