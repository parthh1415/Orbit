"""Tests for app.ingest.gdelt — GDELT event ingestion."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.db import get_db, run_migrations
from app.ingest.gdelt import build_gdelt_description, parse_gdelt_rows, poll_gdelt


def _make_tsv_line(
    event_id: str = "123456789",
    day: str = "20260414",
    actor1_name: str = "UNITED STATES",
    actor1_country: str = "USA",
    actor2_name: str = "CHINA",
    actor2_country: str = "CHN",
    event_code: str = "042",
    goldstein: str = "-3.4",
    num_sources: str = "5",
    num_articles: str = "10",
    action_geo_fullname: str = "Beijing, China",
    lat: str = "39.9",
    lon: str = "116.4",
    source_url: str = "https://example.com/article",
) -> str:
    """Build a 58-column TSV line for GDELT v2 events export."""
    cols = [""] * 58
    cols[0] = event_id
    cols[1] = day
    cols[5] = actor1_name
    cols[7] = actor1_country
    cols[15] = actor2_name
    cols[17] = actor2_country
    cols[26] = event_code
    cols[30] = goldstein
    cols[31] = num_sources
    cols[32] = num_articles
    cols[49] = action_geo_fullname
    cols[53] = lat
    cols[54] = lon
    cols[57] = source_url
    return "\t".join(cols)


class TestBuildGdeltDescription:
    """Tests for the build_gdelt_description helper."""

    def test_full_description(self) -> None:
        result = build_gdelt_description("USA", "CHINA", "172", "Taiwan")
        assert result == "USA imposed sanctions on CHINA in Taiwan"

    def test_no_actor2(self) -> None:
        result = build_gdelt_description("USA", "", "042", "Beijing, China")
        assert result == "USA consulted with in Beijing, China"

    def test_no_actors(self) -> None:
        result = build_gdelt_description("", "", "042", "Beijing, China")
        assert result == "consulted with in Beijing, China"

    def test_no_cameo(self) -> None:
        result = build_gdelt_description("USA", "CHINA", "", "")
        assert result == "USA CHINA"

    def test_empty_all(self) -> None:
        result = build_gdelt_description("", "", "", "")
        assert result == ""

    def test_unknown_cameo_code(self) -> None:
        result = build_gdelt_description("USA", "CHINA", "99", "")
        assert result == "USA CHINA"

    def test_geo_only(self) -> None:
        result = build_gdelt_description("", "", "", "Taiwan")
        assert result == "in Taiwan"


def test_parse_gdelt_rows_basic() -> None:
    """parse_gdelt_rows extracts fields from valid TSV."""
    tsv = _make_tsv_line()
    rows = parse_gdelt_rows(tsv)
    assert len(rows) == 1

    row = rows[0]
    assert row[0] == "gdelt-123456789"  # id
    assert row[1] == "gdelt"  # source
    assert "2026-04-14" in row[2]  # timestamp
    # Description is now human-readable, built from actor names + CAMEO verb
    assert "UNITED STATES" in row[3]
    assert "CHINA" in row[3]
    assert "consulted with" in row[3]  # CAMEO 04 -> "consulted with"
    assert "Beijing" in row[3]
    assert row[4] == "042"  # cameo_code
    assert row[5] == -3.4  # goldstein_score
    assert row[6] == 5  # num_sources
    assert row[7] == 39.9  # lat
    assert row[8] == 116.4  # lon
    countries = json.loads(row[9])
    assert "USA" in countries
    assert "CHN" in countries


def test_parse_gdelt_rows_skips_short_lines() -> None:
    """Lines with fewer than 58 columns are skipped."""
    tsv = "col1\tcol2\tcol3"
    rows = parse_gdelt_rows(tsv)
    assert rows == []


def test_parse_gdelt_rows_skips_empty_event_id() -> None:
    """Lines with an empty GlobalEventID are skipped."""
    tsv = _make_tsv_line(event_id="")
    rows = parse_gdelt_rows(tsv)
    assert rows == []


def test_parse_gdelt_rows_handles_bad_numeric() -> None:
    """Non-numeric goldstein/lat/lon fall back to 0.0."""
    tsv = _make_tsv_line(goldstein="bad", lat="nope", lon="")
    rows = parse_gdelt_rows(tsv)
    assert len(rows) == 1
    assert rows[0][5] == 0.0  # goldstein
    assert rows[0][7] == 0.0  # lat
    assert rows[0][8] == 0.0  # lon


def test_parse_gdelt_rows_multiple() -> None:
    """Multiple TSV lines produce multiple rows."""
    lines = [
        _make_tsv_line(event_id="111"),
        _make_tsv_line(event_id="222"),
        _make_tsv_line(event_id="333"),
    ]
    rows = parse_gdelt_rows("\n".join(lines))
    assert len(rows) == 3
    ids = [r[0] for r in rows]
    assert "gdelt-111" in ids
    assert "gdelt-222" in ids
    assert "gdelt-333" in ids


def test_parse_gdelt_rows_no_url_still_has_readable_description() -> None:
    """Even without a source URL, description is built from actor/CAMEO fields."""
    tsv = _make_tsv_line(source_url="")
    rows = parse_gdelt_rows(tsv)
    assert len(rows) == 1
    desc = rows[0][3]
    # Should contain actor names and CAMEO verb, not a URL or raw event ID
    assert "UNITED STATES" in desc
    assert "CHINA" in desc
    assert not desc.startswith("GDELT event")


def test_parse_gdelt_rows_fallback_when_all_fields_empty() -> None:
    """When actor names, countries, and CAMEO are all empty, falls back to event ID."""
    tsv = _make_tsv_line(
        actor1_name="",
        actor1_country="",
        actor2_name="",
        actor2_country="",
        event_code="",
        action_geo_fullname="",
        source_url="",
    )
    rows = parse_gdelt_rows(tsv)
    assert len(rows) == 1
    assert "GDELT event" in rows[0][3]


def test_parse_gdelt_dedup_countries() -> None:
    """If actor1 and actor2 are the same, only one entry."""
    tsv = _make_tsv_line(actor1_country="USA", actor2_country="USA")
    rows = parse_gdelt_rows(tsv)
    countries = json.loads(rows[0][9])
    assert countries == ["USA"]


async def test_poll_gdelt_demo_mode(tmp_path: Path) -> None:
    """poll_gdelt in demo mode reads from demo_snapshot.json and writes to DB."""
    db_path = str(tmp_path / "test.db")
    await run_migrations(db_path)

    # Create a demo snapshot file
    demo_path = tmp_path / "demo_snapshot.json"
    demo_data = {
        "events": [
            {
                "id": "demo-test-001",
                "source": "gdelt",
                "timestamp": "2026-04-14T08:00:00Z",
                "description": "Test event",
                "cameo_code": "042",
                "goldstein_score": -3.4,
                "num_sources": 5,
                "lat": 39.9,
                "lon": 116.4,
                "countries": '["USA","CHN"]',
                "sentiment": 0.0,
                "metadata": "{}",
            }
        ]
    }
    demo_path.write_text(json.dumps(demo_data), encoding="utf-8")

    # Monkey-patch the demo path
    import app.ingest.gdelt as gdelt_mod

    original_path = gdelt_mod._DEMO_PATH
    gdelt_mod._DEMO_PATH = demo_path  # type: ignore[assignment]
    try:
        settings = Settings(demo_mode=True, database_url=db_path)
        count = await poll_gdelt(settings)
        assert count == 1

        async with get_db(db_path) as db:
            cursor = await db.execute("SELECT id, source FROM events")
            rows = await cursor.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "demo-test-001"
            assert rows[0][1] == "gdelt"
    finally:
        gdelt_mod._DEMO_PATH = original_path  # type: ignore[assignment]
