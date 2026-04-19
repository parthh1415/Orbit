"""ORBIT NewsAPI ingestion — polls every 60 s for headline events."""

from __future__ import annotations

import hashlib
import json
import logging
import pathlib
from datetime import UTC, datetime

import httpx

from app.config import TRACKED_TICKERS, Settings
from app.db import get_db
from app.ingest._demo_time import rebase_event_timestamp

logger = logging.getLogger(__name__)

_DEMO_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "demo_snapshot.json"

_BASE_URL = "https://newsapi.org/v2/everything"


def _url_hash(url: str) -> str:
    """Return a deterministic SHA-256 hex digest for a URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def parse_articles(
    articles: list[dict[str, object]],
    ticker: str,
) -> list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]]:
    """Convert NewsAPI articles into event-table row tuples.

    Returns list of (id, source, timestamp, description, cameo_code,
    goldstein_score, num_sources, lat, lon, countries, sentiment, metadata).
    """
    rows: list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]] = []
    for art in articles:
        url = str(art.get("url", ""))
        if not url:
            continue

        row_id = f"newsapi-{_url_hash(url)}"
        title = str(art.get("title", ""))
        desc_raw = str(art.get("description", ""))
        description = title or desc_raw or url

        published = str(art.get("publishedAt", ""))
        if not published:
            published = datetime.now(tz=UTC).isoformat()

        source_name = ""
        src_obj = art.get("source")
        if isinstance(src_obj, dict):
            source_name = str(src_obj.get("name", ""))

        metadata = json.dumps({"url": url, "source_name": source_name, "ticker": ticker})

        rows.append(
            (
                row_id,
                "newsapi",
                published,
                description,
                "",  # cameo_code
                0.0,  # goldstein_score
                1,  # num_sources
                0.0,  # lat
                0.0,  # lon
                "[]",  # countries
                0.0,  # sentiment — LLM tagger will update later
                metadata,
            )
        )
    return rows


async def _fetch_articles(
    client: httpx.AsyncClient,
    ticker: str,
    api_key: str,
) -> list[dict[str, object]]:
    """Fetch latest articles for *ticker* from NewsAPI."""
    resp = await client.get(
        _BASE_URL,
        params={
            "q": ticker,
            "apiKey": api_key,
            "sortBy": "publishedAt",
            "pageSize": "5",
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    data: dict[str, object] = resp.json()
    articles = data.get("articles")
    if isinstance(articles, list):
        return articles
    return []


async def _ingest_demo(settings: Settings) -> int:
    """Load newsapi events from demo_snapshot.json."""
    if not _DEMO_PATH.exists():
        logger.warning("Demo snapshot not found at %s", _DEMO_PATH)
        return 0

    raw = _DEMO_PATH.read_text(encoding="utf-8")
    data: dict[str, object] = json.loads(raw)
    events = data.get("events")
    if not isinstance(events, list):
        return 0

    now = datetime.now(tz=UTC)
    rows: list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]] = []
    for evt in events:
        if not isinstance(evt, dict):
            continue
        if str(evt.get("source", "")) != "newsapi":
            continue
        event_id = str(evt.get("id", ""))
        rows.append(
            (
                event_id,
                str(evt.get("source", "newsapi")),
                rebase_event_timestamp(event_id, now),
                str(evt.get("description", "")),
                str(evt.get("cameo_code", "")),
                float(evt.get("goldstein_score", 0.0)),
                int(evt.get("num_sources", 1)),
                float(evt.get("lat", 0.0)),
                float(evt.get("lon", 0.0)),
                str(evt.get("countries", "[]")),
                float(evt.get("sentiment", 0.0)),
                str(evt.get("metadata", "{}")),
            )
        )

    if not rows:
        return 0

    async with get_db(settings.database_url) as db:
        await db.executemany(
            """INSERT OR IGNORE INTO events
               (id, source, timestamp, description, cameo_code,
                goldstein_score, num_sources, lat, lon,
                countries, sentiment, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await db.commit()

    return len(rows)


async def poll_news(settings: Settings) -> int:
    """Poll NewsAPI for articles related to tracked tickers.

    Returns total number of new event rows written.
    """
    if settings.demo_mode:
        return await _ingest_demo(settings)

    total = 0
    try:
        async with httpx.AsyncClient() as client:
            for ticker in TRACKED_TICKERS:
                try:
                    articles = await _fetch_articles(client, ticker, settings.newsapi_key)
                    rows = parse_articles(articles, ticker)
                    if not rows:
                        continue

                    async with get_db(settings.database_url) as db:
                        await db.executemany(
                            """INSERT OR IGNORE INTO events
                               (id, source, timestamp, description,
                                cameo_code, goldstein_score, num_sources,
                                lat, lon, countries, sentiment, metadata)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            rows,
                        )
                        await db.commit()

                    total += len(rows)
                except httpx.HTTPError as exc:
                    logger.error("NewsAPI HTTP error for %s: %s", ticker, exc)
                except Exception:
                    logger.exception("NewsAPI error for %s", ticker)

    except Exception:
        logger.exception("NewsAPI unexpected error")

    if total:
        logger.info("NewsAPI: ingested %d articles", total)
    return total
