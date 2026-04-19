"""ORBIT historical replay engine — replays a trading day at accelerated speed.

Phase A: pre-fetch GDELT events, Alpaca bars, and NewsAPI articles for the
replay date and cache them in memory.

Phase B: run an async loop that drips cached data into SQLite with rebased
timestamps so the scoring engine's recency_decay works without modification.
"""

from __future__ import annotations

import asyncio
import calendar
import io
import json
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import TRACKED_TICKERS, Settings
from app.db import get_db
from app.ingest.alpaca import parse_bars
from app.ingest.gdelt import parse_gdelt_rows
from app.ingest.news import parse_articles
from app.scoring.correlation import exposure_weight, relevance
from app.scoring.verdict import direction_from_goldstein

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GDELT country-name -> ISO-2 mapping
# ---------------------------------------------------------------------------

GDELT_TO_ISO: dict[str, str] = {
    # United States
    "UNITED STATES": "US",
    "THE US": "US",
    "AMERICAN": "US",
    "USA": "US",
    "USG": "US",
    # China
    "CHINA": "CN",
    "CHINESE": "CN",
    "CHN": "CN",
    # Taiwan
    "TAIWAN": "TW",
    "TAIWANESE": "TW",
    "TWN": "TW",
    # Japan
    "JAPAN": "JP",
    "JAPANESE": "JP",
    "JPN": "JP",
    # South Korea
    "SOUTH KOREA": "KR",
    "SOUTH KOREAN": "KR",
    "KOREAN": "KR",
    "KOR": "KR",
    # North Korea
    "NORTH KOREA": "KP",
    "PRK": "KP",
}

# ---------------------------------------------------------------------------
# Market hours in UTC (9:30 AM - 4:00 PM ET = 13:30 - 21:00 UTC)
# ---------------------------------------------------------------------------

_MARKET_OPEN_UTC_HOUR = 13
_MARKET_OPEN_UTC_MIN = 30
_MARKET_CLOSE_UTC_HOUR = 21
_MARKET_CLOSE_UTC_MIN = 0

# ---------------------------------------------------------------------------
# GDELT archive URL template (15-minute windows)
# ---------------------------------------------------------------------------

_GDELT_ARCHIVE_URL = "http://data.gdeltproject.org/gdeltv2/{ts}.export.CSV.zip"

# ---------------------------------------------------------------------------
# Alpaca historical bars endpoint
# ---------------------------------------------------------------------------

_ALPACA_BASE_URL = "https://data.alpaca.markets"

# ---------------------------------------------------------------------------
# NewsAPI endpoint
# ---------------------------------------------------------------------------

_NEWSAPI_BASE_URL = "https://newsapi.org/v2/everything"

# ---------------------------------------------------------------------------
# Yahoo Finance chart endpoint (historical 1-min bars fallback)
# ---------------------------------------------------------------------------

_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_YAHOO_USER_AGENT = "Mozilla/5.0"


# ---------------------------------------------------------------------------
# Cached data container
# ---------------------------------------------------------------------------


@dataclass
class ReplayCache:
    """In-memory cache of pre-fetched data for the replay day."""

    events: list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]] = (
        field(default_factory=list)
    )
    bars: list[tuple[str, str, float, float, float, float, int]] = field(default_factory=list)
    articles: list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]] = (
        field(default_factory=list)
    )

    # Original timestamps for ordering (parallel lists with above)
    event_timestamps: list[datetime] = field(default_factory=list)
    bar_timestamps: list[datetime] = field(default_factory=list)
    article_timestamps: list[datetime] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_countries(countries_json: str) -> str:
    """Convert GDELT country names/codes in a JSON array to ISO-2 codes.

    Handles 3-letter CAMEO codes (``USA`` -> ``US``), full country names
    (``UNITED STATES`` -> ``US``), and already-valid ISO-2 codes (``US``
    passes through unchanged).  The fallback for unmapped entries is the
    uppercased input so that case mismatches never cause a miss against
    ``exposure.json``.
    """
    try:
        raw: list[str] = json.loads(countries_json)
    except (json.JSONDecodeError, TypeError):
        return "[]"

    normalised: list[str] = []
    for name in raw:
        upper = name.upper()
        iso = GDELT_TO_ISO.get(upper, upper)
        if iso not in normalised:
            normalised.append(iso)
    return json.dumps(normalised)


def _parse_ts(ts_str: str) -> datetime:
    """Parse an ISO-8601 or similar timestamp to a tz-aware datetime."""
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _gdelt_window_timestamps(replay_date: str) -> list[str]:
    """Return GDELT 15-minute archive timestamps for a full trading day.

    GDELT publishes files every 15 minutes.  We cover 14:30 -> 21:00 UTC
    (plus a small buffer before open).  Timestamps are formatted as
    ``YYYYMMDDHHMMSS``.
    """
    base = datetime.strptime(replay_date, "%Y-%m-%d").replace(tzinfo=UTC)
    # Start fetching 1 hour before market open for pre-market context
    start = base.replace(hour=12, minute=30, second=0, microsecond=0)
    end = base.replace(hour=21, minute=15, second=0, microsecond=0)

    stamps: list[str] = []
    current = start
    while current <= end:
        stamps.append(current.strftime("%Y%m%d%H%M%S"))
        current += timedelta(minutes=15)
    return stamps


# ---------------------------------------------------------------------------
# Phase A — Pre-fetch
# ---------------------------------------------------------------------------


async def _prefetch_gdelt(
    client: httpx.AsyncClient,
    replay_date: str,
) -> tuple[
    list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]],
    list[datetime],
]:
    """Download and parse GDELT archives for the replay date."""
    timestamps = _gdelt_window_timestamps(replay_date)
    all_rows: list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]] = []
    all_ts: list[datetime] = []

    logger.info("REPLAY prefetch: downloading %d GDELT windows", len(timestamps))

    for ts_str in timestamps:
        url = _GDELT_ARCHIVE_URL.format(ts=ts_str)
        try:
            resp = await client.get(url, timeout=30.0)
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                for name in zf.namelist():
                    if name.endswith(".CSV"):
                        tsv_text = zf.read(name).decode("utf-8", errors="replace")
                        rows = parse_gdelt_rows(tsv_text)
                        for row in rows:
                            # Normalise countries to ISO codes
                            normalised = (
                                row[0],
                                row[1],
                                row[2],
                                row[3],
                                row[4],
                                row[5],
                                row[6],
                                row[7],
                                row[8],
                                _normalize_countries(row[9]),
                                row[10],
                                row[11],
                            )
                            all_rows.append(normalised)
                            all_ts.append(_parse_ts(row[2]))
        except (httpx.HTTPError, zipfile.BadZipFile, OSError) as exc:
            logger.warning("REPLAY: GDELT window %s failed: %s", ts_str, exc)
            continue

    # Sort by timestamp
    if all_rows:
        paired = sorted(zip(all_ts, all_rows, strict=True), key=lambda x: x[0])
        all_ts = [p[0] for p in paired]
        all_rows = [p[1] for p in paired]

    logger.info("REPLAY prefetch: %d GDELT events cached", len(all_rows))
    return all_rows, all_ts


async def _prefetch_alpaca(
    client: httpx.AsyncClient,
    settings: Settings,
    replay_date: str,
) -> tuple[list[tuple[str, str, float, float, float, float, int]], list[datetime]]:
    """Fetch Alpaca historical 1-min bars for all tracked tickers on the replay date."""
    all_rows: list[tuple[str, str, float, float, float, float, int]] = []
    all_ts: list[datetime] = []

    start = f"{replay_date}T13:30:00Z"
    end = f"{replay_date}T21:00:00Z"

    for ticker in TRACKED_TICKERS:
        try:
            resp = await client.get(
                f"{_ALPACA_BASE_URL}/v2/stocks/{ticker}/bars",
                params={
                    "timeframe": "1Min",
                    "start": start,
                    "end": end,
                    "limit": "10000",
                },
                headers={
                    "APCA-API-KEY-ID": settings.alpaca_api_key,
                    "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data: dict[str, object] = resp.json()
            bars_json = data.get("bars")
            if isinstance(bars_json, list):
                rows = parse_bars(ticker, bars_json)
                for row in rows:
                    all_rows.append(row)
                    all_ts.append(_parse_ts(row[1]))
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "REPLAY: Alpaca %s HTTP %d: %s",
                ticker,
                exc.response.status_code,
                exc,
            )
            continue
        except httpx.HTTPError as exc:
            logger.warning("REPLAY: Alpaca %s failed: %s", ticker, exc)
            continue

    # Sort by timestamp
    if all_rows:
        paired = sorted(zip(all_ts, all_rows, strict=True), key=lambda x: x[0])
        all_ts = [p[0] for p in paired]
        all_rows = [p[1] for p in paired]

    logger.info("REPLAY prefetch: %d Alpaca bars cached", len(all_rows))
    return all_rows, all_ts


def _replay_date_to_market_unix(replay_date: str) -> tuple[int, int]:
    """Compute UNIX timestamps for US market open/close on *replay_date*.

    Returns ``(period1, period2)`` where period1 is 9:30 AM ET (13:30 UTC)
    and period2 is 4:00 PM ET (20:00 UTC) for the given date.
    """
    base = datetime.strptime(replay_date, "%Y-%m-%d").replace(tzinfo=UTC)
    market_open = base.replace(
        hour=_MARKET_OPEN_UTC_HOUR,
        minute=_MARKET_OPEN_UTC_MIN,
        second=0,
        microsecond=0,
    )
    market_close = base.replace(
        hour=_MARKET_CLOSE_UTC_HOUR,
        minute=_MARKET_CLOSE_UTC_MIN,
        second=0,
        microsecond=0,
    )
    return int(calendar.timegm(market_open.timetuple())), int(
        calendar.timegm(market_close.timetuple())
    )


async def _prefetch_yahoo(
    client: httpx.AsyncClient,
    replay_date: str,
) -> tuple[list[tuple[str, str, float, float, float, float, int]], list[datetime]]:
    """Fetch Yahoo Finance 1-min historical bars as a fallback for Alpaca.

    Yahoo Finance serves historical data even on weekends, making it a
    reliable source for replay back-testing when Alpaca returns nothing.
    """
    all_rows: list[tuple[str, str, float, float, float, float, int]] = []
    all_ts: list[datetime] = []

    period1, period2 = _replay_date_to_market_unix(replay_date)

    for ticker in TRACKED_TICKERS:
        url = _YAHOO_CHART_URL.format(ticker=ticker)
        try:
            resp = await client.get(
                url,
                params={
                    "interval": "5m",
                    "period1": str(period1),
                    "period2": str(period2),
                },
                headers={"User-Agent": _YAHOO_USER_AGENT},
                timeout=30.0,
            )
            resp.raise_for_status()
            data: dict[str, object] = resp.json()

            chart = data.get("chart")
            if not isinstance(chart, dict):
                logger.warning("REPLAY: Yahoo %s — unexpected top-level shape", ticker)
                continue

            results = chart.get("result")
            if not isinstance(results, list) or len(results) == 0:
                logger.warning("REPLAY: Yahoo %s — empty result list", ticker)
                continue

            result_obj = results[0]
            if not isinstance(result_obj, dict):
                continue

            timestamps_raw = result_obj.get("timestamp")
            if not isinstance(timestamps_raw, list):
                logger.warning("REPLAY: Yahoo %s — no timestamps", ticker)
                continue

            indicators = result_obj.get("indicators")
            if not isinstance(indicators, dict):
                continue

            quote_list = indicators.get("quote")
            if not isinstance(quote_list, list) or len(quote_list) == 0:
                continue

            quote = quote_list[0]
            if not isinstance(quote, dict):
                continue

            opens = quote.get("open")
            highs = quote.get("high")
            lows = quote.get("low")
            closes = quote.get("close")
            volumes = quote.get("volume")

            if not all(isinstance(x, list) for x in [opens, highs, lows, closes, volumes]):
                continue

            # Type-narrow for mypy: these are all list[Any] at this point
            assert isinstance(opens, list)
            assert isinstance(highs, list)
            assert isinstance(lows, list)
            assert isinstance(closes, list)
            assert isinstance(volumes, list)

            for i, ts_unix in enumerate(timestamps_raw):
                if i >= len(opens):
                    break
                o_val = opens[i]
                h_val = highs[i]
                l_val = lows[i]
                c_val = closes[i]
                v_val = volumes[i]

                # Yahoo returns None for bars outside market hours
                if any(x is None for x in (o_val, h_val, l_val, c_val, v_val)):
                    continue

                ts_dt = datetime.fromtimestamp(int(ts_unix), tz=UTC)
                ts_iso = ts_dt.isoformat()
                all_rows.append(
                    (
                        ticker,
                        ts_iso,
                        float(o_val),
                        float(h_val),
                        float(l_val),
                        float(c_val),
                        int(v_val),
                    )
                )
                all_ts.append(ts_dt)

        except httpx.HTTPError as exc:
            logger.warning("REPLAY: Yahoo %s HTTP error: %s", ticker, exc)
            continue
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("REPLAY: Yahoo %s parse error: %s", ticker, exc)
            continue

    # Sort by timestamp
    if all_rows:
        paired = sorted(zip(all_ts, all_rows, strict=True), key=lambda x: x[0])
        all_ts = [p[0] for p in paired]
        all_rows = [p[1] for p in paired]

    logger.info("REPLAY prefetch: %d Yahoo Finance bars cached", len(all_rows))
    return all_rows, all_ts


async def _prefetch_news(
    client: httpx.AsyncClient,
    settings: Settings,
    replay_date: str,
) -> tuple[
    list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]],
    list[datetime],
]:
    """Fetch NewsAPI articles for all tracked tickers on the replay date."""
    all_rows: list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]] = []
    all_ts: list[datetime] = []

    for ticker in TRACKED_TICKERS:
        try:
            resp = await client.get(
                _NEWSAPI_BASE_URL,
                params={
                    "q": ticker,
                    "apiKey": settings.newsapi_key,
                    "from": replay_date,
                    "to": replay_date,
                    "sortBy": "publishedAt",
                    "pageSize": "20",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data: dict[str, object] = resp.json()
            articles = data.get("articles")
            if isinstance(articles, list):
                rows = parse_articles(articles, ticker)
                for row in rows:
                    published_str = str(row[2])
                    all_rows.append(row)
                    all_ts.append(_parse_ts(published_str))
        except httpx.HTTPError as exc:
            logger.warning("REPLAY: NewsAPI %s failed: %s", ticker, exc)
            continue

    # Sort by timestamp
    if all_rows:
        paired = sorted(zip(all_ts, all_rows, strict=True), key=lambda x: x[0])
        all_ts = [p[0] for p in paired]
        all_rows = [p[1] for p in paired]

    logger.info("REPLAY prefetch: %d NewsAPI articles cached", len(all_rows))
    return all_rows, all_ts


async def prefetch_replay_data(settings: Settings) -> ReplayCache:
    """Download and cache all data for the replay date (Phase A)."""
    cache = ReplayCache()

    async with httpx.AsyncClient() as client:
        gdelt_rows, gdelt_ts = await _prefetch_gdelt(client, settings.replay_date)
        cache.events = gdelt_rows
        cache.event_timestamps = gdelt_ts

        alpaca_rows, alpaca_ts = await _prefetch_alpaca(client, settings, settings.replay_date)
        if alpaca_rows:
            cache.bars = alpaca_rows
            cache.bar_timestamps = alpaca_ts
        else:
            logger.info("REPLAY: Alpaca returned 0 bars — falling back to Yahoo Finance")
            yahoo_rows, yahoo_ts = await _prefetch_yahoo(client, settings.replay_date)
            cache.bars = yahoo_rows
            cache.bar_timestamps = yahoo_ts

        news_rows, news_ts = await _prefetch_news(client, settings, settings.replay_date)
        cache.articles = news_rows
        cache.article_timestamps = news_ts

    total = len(cache.events) + len(cache.bars) + len(cache.articles)
    logger.info(
        "REPLAY prefetch complete: %d events, %d bars, %d articles (total %d)",
        len(cache.events),
        len(cache.bars),
        len(cache.articles),
        total,
    )
    return cache


# ---------------------------------------------------------------------------
# Timestamp rebasing
# ---------------------------------------------------------------------------


def rebase_timestamp(
    item_ts: datetime,
    replay_clock: datetime,
    real_now: datetime,
) -> str:
    """Rebase an item's replay timestamp so it appears recent in real time.

    The offset between the item and the current replay clock position is
    preserved, then applied backwards from *real_now*.

    Example: if the replay clock is at 10:00 AM and the item occurred at
    9:45 AM (15 min ago in replay time), the rebased timestamp will be
    ``real_now - 15 minutes``.
    """
    offset = replay_clock - item_ts
    # Clamp negative offsets (item is "in the future" relative to clock)
    if offset.total_seconds() < 0:
        offset = timedelta(seconds=0)
    rebased = real_now - offset
    return rebased.isoformat()


# ---------------------------------------------------------------------------
# Event scoring helper (deterministic, no LLM)
# ---------------------------------------------------------------------------


def _score_event_for_tickers(
    countries_json: str,
    goldstein_score: float,
    num_sources: int,
) -> list[tuple[str, float, str]]:
    """Score an event against each tracked ticker.

    Countries are normalised to ISO-2 codes before looking up exposure
    weights so that raw GDELT names/codes (``"USA"``, ``"UNITED STATES"``)
    are correctly matched against ``exposure.json``.

    Returns list of (ticker, relevance_score, implied_direction).
    """
    # Normalise to ISO-2 to guard against un-normalised upstream data
    iso_json = _normalize_countries(countries_json)
    try:
        countries: list[str] = json.loads(iso_json)
    except (json.JSONDecodeError, TypeError):
        countries = []

    results: list[tuple[str, float, str]] = []
    direction = direction_from_goldstein(goldstein_score)

    for ticker in TRACKED_TICKERS:
        # Find best exposure country
        best_weight = 0.0
        best_code = ""
        for code in countries:
            w = exposure_weight(code, ticker)
            if w > best_weight:
                best_weight = w
                best_code = code

        score = relevance(
            location=best_code,
            ticker=ticker,
            goldstein_score=goldstein_score,
            hours_since_event=0.0,  # Just inserted — 0 hours old
            num_sources=num_sources,
        )
        if score > 0.0:
            results.append((ticker, score, direction.value))

    return results


# ---------------------------------------------------------------------------
# Phase B — Replay loop
# ---------------------------------------------------------------------------


async def start_replay(settings: Settings, cache: ReplayCache) -> None:
    """Run the accelerated replay loop (Phase B).

    Advances the replay clock at ``settings.replay_speed`` x real time,
    inserting cached data with rebased timestamps as the clock passes each
    item's original timestamp.
    """
    replay_date = datetime.strptime(settings.replay_date, "%Y-%m-%d").replace(tzinfo=UTC)
    market_open = replay_date.replace(
        hour=_MARKET_OPEN_UTC_HOUR,
        minute=_MARKET_OPEN_UTC_MIN,
        second=0,
        microsecond=0,
    )
    market_close = replay_date.replace(
        hour=_MARKET_CLOSE_UTC_HOUR,
        minute=_MARKET_CLOSE_UTC_MIN,
        second=0,
        microsecond=0,
    )

    replay_clock = market_open
    real_start = datetime.now(tz=UTC)

    # Cursors into the sorted cache lists
    event_cursor = 0
    bar_cursor = 0
    article_cursor = 0

    # Stats
    total_events_inserted = 0
    total_bars_inserted = 0
    total_articles_inserted = 0
    total_scores_inserted = 0

    # Track latest bar close per ticker for log output
    latest_close: dict[str, float] = {}
    first_close: dict[str, float] = {}

    logger.info(
        "REPLAY started: %s at %dx speed (market open %s -> close %s)",
        settings.replay_date,
        settings.replay_speed,
        market_open.strftime("%H:%M UTC"),
        market_close.strftime("%H:%M UTC"),
    )

    while replay_clock < market_close:
        real_now = datetime.now(tz=UTC)
        elapsed_real = (real_now - real_start).total_seconds()
        replay_clock = market_open + timedelta(seconds=elapsed_real * settings.replay_speed)

        if replay_clock >= market_close:
            replay_clock = market_close

        # --- Collect items whose timestamp <= replay_clock ---
        batch_events: list[
            tuple[str, str, str, str, str, float, int, float, float, str, float, str]
        ] = []
        batch_event_ts: list[datetime] = []
        # Cap batch size to prevent blocking the event loop on dense windows
        max_per_tick = 500
        while event_cursor < len(cache.events) and len(batch_events) < max_per_tick:
            if cache.event_timestamps[event_cursor] <= replay_clock:
                batch_events.append(cache.events[event_cursor])
                batch_event_ts.append(cache.event_timestamps[event_cursor])
                event_cursor += 1
            else:
                break

        batch_bars: list[tuple[str, str, float, float, float, float, int]] = []
        batch_bar_ts: list[datetime] = []
        while bar_cursor < len(cache.bars):
            if cache.bar_timestamps[bar_cursor] <= replay_clock:
                batch_bars.append(cache.bars[bar_cursor])
                batch_bar_ts.append(cache.bar_timestamps[bar_cursor])
                bar_cursor += 1
            else:
                break

        batch_articles: list[
            tuple[str, str, str, str, str, float, int, float, float, str, float, str]
        ] = []
        batch_article_ts: list[datetime] = []
        while article_cursor < len(cache.articles):
            if cache.article_timestamps[article_cursor] <= replay_clock:
                batch_articles.append(cache.articles[article_cursor])
                batch_article_ts.append(cache.article_timestamps[article_cursor])
                article_cursor += 1
            else:
                break

        # --- Insert batches with rebased timestamps ---
        batch_event_count = 0
        batch_bar_count = 0
        batch_article_count = 0
        batch_score_count = 0

        if batch_events:
            rebased_rows: list[
                tuple[str, str, str, str, str, float, int, float, float, str, float, str]
            ] = []
            score_rows: list[tuple[str, str, float, str, str]] = []
            for row, orig_ts in zip(batch_events, batch_event_ts, strict=True):
                rebased_ts = rebase_timestamp(orig_ts, replay_clock, real_now)
                rebased = (
                    row[0],
                    row[1],
                    rebased_ts,
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    row[7],
                    row[8],
                    row[9],
                    row[10],
                    row[11],
                )
                rebased_rows.append(rebased)

                # Score against each ticker
                scores = _score_event_for_tickers(row[9], row[5], row[6])
                for ticker, score, direction in scores:
                    score_rows.append((row[0], ticker, score, direction, rebased_ts))

            # Yield to event loop before DB write so HTTP requests aren't starved
            await asyncio.sleep(0)
            async with get_db(settings.database_url) as db:
                await db.executemany(
                    """INSERT OR IGNORE INTO events
                       (id, source, timestamp, description, cameo_code,
                        goldstein_score, num_sources, lat, lon,
                        countries, sentiment, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    rebased_rows,
                )
                if score_rows:
                    await db.executemany(
                        """INSERT OR IGNORE INTO event_scores
                           (event_id, ticker, relevance, implied_direction, computed_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        score_rows,
                    )
                await db.commit()
            batch_event_count = len(rebased_rows)
            batch_score_count = len(score_rows)

        if batch_bars:
            rebased_bar_rows: list[tuple[str, str, float, float, float, float, int]] = []
            for bar_row, bar_orig_ts in zip(batch_bars, batch_bar_ts, strict=True):
                rebased_ts = rebase_timestamp(bar_orig_ts, replay_clock, real_now)
                rebased_bar_rows.append(
                    (
                        bar_row[0],
                        rebased_ts,
                        bar_row[2],
                        bar_row[3],
                        bar_row[4],
                        bar_row[5],
                        bar_row[6],
                    )
                )
                # Track prices for logging
                ticker = bar_row[0]
                close_price = bar_row[5]
                latest_close[ticker] = close_price
                if ticker not in first_close:
                    first_close[ticker] = close_price

            async with get_db(settings.database_url) as db:
                await db.executemany(
                    """INSERT OR IGNORE INTO bars
                       (ticker, timestamp, open, high, low, close, volume)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    rebased_bar_rows,
                )
                # Update price_cache with latest close per ticker
                price_updates: list[tuple[str, float, str]] = []
                for bar_row in rebased_bar_rows:
                    price_updates.append((bar_row[0], bar_row[5], bar_row[1]))
                if price_updates:
                    await db.executemany(
                        """INSERT INTO price_cache (ticker, price, updated_at)
                           VALUES (?, ?, ?)
                           ON CONFLICT(ticker) DO UPDATE
                           SET price = excluded.price,
                               updated_at = excluded.updated_at""",
                        price_updates,
                    )
                await db.commit()
            batch_bar_count = len(rebased_bar_rows)

        if batch_articles:
            rebased_article_rows: list[
                tuple[str, str, str, str, str, float, int, float, float, str, float, str]
            ] = []
            article_score_rows: list[tuple[str, str, float, str, str]] = []
            for art_row, art_orig_ts in zip(batch_articles, batch_article_ts, strict=True):
                rebased_ts = rebase_timestamp(art_orig_ts, replay_clock, real_now)
                rebased = (
                    art_row[0],
                    art_row[1],
                    rebased_ts,
                    art_row[3],
                    art_row[4],
                    art_row[5],
                    art_row[6],
                    art_row[7],
                    art_row[8],
                    art_row[9],
                    art_row[10],
                    art_row[11],
                )
                rebased_article_rows.append(rebased)

                # Score articles through the same relevance formula as
                # GDELT events so they are not stuck at a flat 0.3 default.
                art_scores = _score_event_for_tickers(art_row[9], art_row[5], art_row[6])
                if art_scores:
                    for art_ticker, art_score, art_dir in art_scores:
                        article_score_rows.append(
                            (art_row[0], art_ticker, art_score, art_dir, rebased_ts)
                        )
                else:
                    # Fallback: if article has no country/goldstein data,
                    # use the ticker from metadata with a minimal score so
                    # the article still appears in the feed.
                    try:
                        meta: dict[str, Any] = json.loads(art_row[11])
                        meta_ticker = str(meta.get("ticker", ""))
                    except (json.JSONDecodeError, TypeError):
                        meta_ticker = ""
                    if meta_ticker in TRACKED_TICKERS:
                        article_score_rows.append(
                            (art_row[0], meta_ticker, 0.1, "flat", rebased_ts)
                        )

            async with get_db(settings.database_url) as db:
                await db.executemany(
                    """INSERT OR IGNORE INTO events
                       (id, source, timestamp, description, cameo_code,
                        goldstein_score, num_sources, lat, lon,
                        countries, sentiment, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    rebased_article_rows,
                )
                if article_score_rows:
                    await db.executemany(
                        """INSERT OR IGNORE INTO event_scores
                           (event_id, ticker, relevance, implied_direction, computed_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        article_score_rows,
                    )
                await db.commit()
            batch_article_count = len(rebased_article_rows)
            batch_score_count += len(article_score_rows)

        total_events_inserted += batch_event_count
        total_bars_inserted += batch_bar_count
        total_articles_inserted += batch_article_count
        total_scores_inserted += batch_score_count

        # --- Log progress ---
        if batch_event_count or batch_bar_count or batch_article_count:
            # Format replay time as ET (UTC - 4 for EDT)
            et_time = replay_clock - timedelta(hours=4)
            time_label = et_time.strftime("%I:%M %p")

            # Price changes
            price_parts: list[str] = []
            for t in TRACKED_TICKERS:
                if t in latest_close and t in first_close and first_close[t] > 0:
                    pct = ((latest_close[t] - first_close[t]) / first_close[t]) * 100
                    sign = "+" if pct >= 0 else ""
                    price_parts.append(f"{t} {sign}{pct:.1f}%")

            price_str = " ".join(price_parts) if price_parts else "no bars yet"
            logger.info(
                "REPLAY %s \u00b7 %d events \u00b7 %d bars \u00b7 %s",
                time_label,
                batch_event_count + batch_article_count,
                batch_bar_count,
                price_str,
            )

        await asyncio.sleep(1.0)

    # --- Final stats ---
    logger.info(
        "REPLAY complete: %d events, %d bars, %d articles, %d scores inserted",
        total_events_inserted,
        total_bars_inserted,
        total_articles_inserted,
        total_scores_inserted,
    )
    logger.info(
        "REPLAY final prices: %s",
        " ".join(f"{t}=${latest_close.get(t, 0.0):.2f}" for t in TRACKED_TICKERS),
    )
