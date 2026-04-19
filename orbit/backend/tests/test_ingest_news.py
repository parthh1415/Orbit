"""Tests for app.ingest.news — NewsAPI ingestion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.db import get_db, run_migrations
from app.ingest.news import _url_hash, parse_articles


def test_url_hash_deterministic() -> None:
    """_url_hash produces the same hash for the same URL."""
    url = "https://example.com/article"
    assert _url_hash(url) == _url_hash(url)
    expected = hashlib.sha256(url.encode("utf-8")).hexdigest()
    assert _url_hash(url) == expected


def test_url_hash_different_urls() -> None:
    """Different URLs produce different hashes."""
    assert _url_hash("https://a.com") != _url_hash("https://b.com")


def test_parse_articles_basic() -> None:
    """parse_articles extracts fields from a well-formed article."""
    articles: list[dict[str, object]] = [
        {
            "url": "https://example.com/news/1",
            "title": "AAPL surges on earnings",
            "description": "Apple Inc reported strong earnings...",
            "publishedAt": "2026-04-14T10:00:00Z",
            "source": {"name": "Example News"},
        }
    ]
    rows = parse_articles(articles, "AAPL")
    assert len(rows) == 1

    row = rows[0]
    assert row[0].startswith("newsapi-")  # id
    assert row[1] == "newsapi"  # source
    assert row[2] == "2026-04-14T10:00:00Z"  # timestamp
    assert row[3] == "AAPL surges on earnings"  # description (title preferred)
    assert row[10] == 0.0  # sentiment
    meta = json.loads(row[11])
    assert meta["ticker"] == "AAPL"
    assert meta["source_name"] == "Example News"


def test_parse_articles_skips_empty_url() -> None:
    """Articles without a URL are skipped."""
    articles: list[dict[str, object]] = [
        {"url": "", "title": "No URL article"},
    ]
    rows = parse_articles(articles, "AAPL")
    assert rows == []


def test_parse_articles_dedup_by_url() -> None:
    """Duplicate URLs produce the same ID (for INSERT OR IGNORE dedup)."""
    url = "https://example.com/same-article"
    articles: list[dict[str, object]] = [
        {"url": url, "title": "First"},
        {"url": url, "title": "Second"},
    ]
    rows = parse_articles(articles, "AAPL")
    assert len(rows) == 2
    # Same URL -> same id
    assert rows[0][0] == rows[1][0]


def test_parse_articles_fallback_description() -> None:
    """If title is empty, description is used; if both empty, URL is used."""
    articles: list[dict[str, object]] = [
        {"url": "https://a.com", "title": "", "description": "Desc text"},
        {"url": "https://b.com", "title": "", "description": ""},
    ]
    rows = parse_articles(articles, "NVDA")
    assert rows[0][3] == "Desc text"
    assert rows[1][3] == "https://b.com"


def test_parse_articles_multiple() -> None:
    """Multiple articles produce multiple rows."""
    articles: list[dict[str, object]] = [
        {"url": f"https://example.com/{i}", "title": f"Article {i}"} for i in range(5)
    ]
    rows = parse_articles(articles, "TSM")
    assert len(rows) == 5


async def test_parse_articles_writes_to_db(tmp_path: Path) -> None:
    """Parsed articles can be written to the events table."""
    db_path = str(tmp_path / "test.db")
    await run_migrations(db_path)

    articles: list[dict[str, object]] = [
        {
            "url": "https://example.com/test",
            "title": "Test article",
            "publishedAt": "2026-04-14T10:00:00Z",
            "source": {"name": "Test"},
        }
    ]
    rows = parse_articles(articles, "AAPL")

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
        cursor = await db.execute("SELECT COUNT(*) FROM events")
        result = await cursor.fetchone()
        assert result is not None
        assert result[0] == 1
