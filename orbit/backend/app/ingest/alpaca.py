"""ORBIT Alpaca market-data ingestion — polls 1-min bars every 60 s."""

from __future__ import annotations

import json
import logging
import pathlib
from datetime import UTC, datetime, timedelta

import httpx

from app.config import TRACKED_TICKERS, Settings
from app.db import get_db

logger = logging.getLogger(__name__)

_DEMO_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "demo_snapshot.json"

_BASE_URL = "https://data.alpaca.markets"


def parse_bars(
    ticker: str, bars_json: list[dict[str, object]]
) -> list[tuple[str, str, float, float, float, float, int]]:
    """Parse Alpaca bars JSON into row tuples for the bars table.

    Returns list of (ticker, timestamp, open, high, low, close, volume).
    """
    rows: list[tuple[str, str, float, float, float, float, int]] = []
    for bar in bars_json:
        ts = str(bar.get("t", ""))
        o = float(str(bar.get("o", 0.0)))
        h = float(str(bar.get("h", 0.0)))
        lo = float(str(bar.get("l", 0.0)))
        c = float(str(bar.get("c", 0.0)))
        v = int(float(str(bar.get("v", 0))))
        if ts:
            rows.append((ticker, ts, o, h, lo, c, v))
    return rows


async def _fetch_bars(
    client: httpx.AsyncClient,
    ticker: str,
    api_key: str,
    secret_key: str,
) -> list[dict[str, object]]:
    """Fetch the latest 1-min bars for a single ticker."""
    now = datetime.now(tz=UTC)
    start = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    resp = await client.get(
        f"{_BASE_URL}/v2/stocks/{ticker}/bars",
        params={"timeframe": "1Min", "start": start, "limit": "5"},
        headers={
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    data: dict[str, object] = resp.json()
    bars = data.get("bars")
    if isinstance(bars, list):
        return bars
    return []


async def _ingest_demo(settings: Settings) -> int:
    """Load bar data from demo_snapshot.json."""
    if not _DEMO_PATH.exists():
        logger.warning("Demo snapshot not found at %s", _DEMO_PATH)
        return 0

    raw = _DEMO_PATH.read_text(encoding="utf-8")
    data: dict[str, object] = json.loads(raw)
    bars = data.get("bars")
    if not isinstance(bars, list):
        return 0

    rows: list[tuple[str, str, float, float, float, float, int]] = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        rows.append(
            (
                str(bar.get("ticker", "")),
                str(bar.get("timestamp", "")),
                float(bar.get("open", 0.0)),
                float(bar.get("high", 0.0)),
                float(bar.get("low", 0.0)),
                float(bar.get("close", 0.0)),
                int(bar.get("volume", 0)),
            )
        )

    if not rows:
        return 0

    async with get_db(settings.database_url) as db:
        await db.executemany(
            """INSERT OR IGNORE INTO bars
               (ticker, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await db.commit()

    return len(rows)


async def poll_alpaca(settings: Settings) -> int:
    """Poll Alpaca for latest 1-min bars across tracked tickers.

    Returns the total number of new bar rows written.
    """
    if settings.demo_mode:
        return await _ingest_demo(settings)

    total = 0
    try:
        async with httpx.AsyncClient() as client:
            for ticker in TRACKED_TICKERS:
                try:
                    bars_json = await _fetch_bars(
                        client,
                        ticker,
                        settings.alpaca_api_key,
                        settings.alpaca_secret_key,
                    )
                    rows = parse_bars(ticker, bars_json)
                    if not rows:
                        continue

                    async with get_db(settings.database_url) as db:
                        await db.executemany(
                            """INSERT OR IGNORE INTO bars
                               (ticker, timestamp, open, high, low, close, volume)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            rows,
                        )
                        await db.commit()

                    total += len(rows)
                except httpx.HTTPStatusError as exc:
                    logger.error(
                        "Alpaca HTTP %d for %s: %s",
                        exc.response.status_code,
                        ticker,
                        exc,
                    )
                except httpx.HTTPError as exc:
                    logger.error("Alpaca HTTP error for %s: %s", ticker, exc)
                except Exception:
                    logger.exception("Alpaca error for %s", ticker)

    except Exception:
        logger.exception("Alpaca unexpected error")

    if total:
        logger.info("Alpaca: ingested %d bars", total)
    return total
