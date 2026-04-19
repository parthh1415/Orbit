"""Tests for app.ingest.alpaca — Alpaca market data ingestion."""

from __future__ import annotations

from app.ingest.alpaca import parse_bars


def test_parse_bars_basic() -> None:
    """parse_bars extracts OHLCV from well-formed Alpaca bar JSON."""
    bars_json: list[dict[str, object]] = [
        {
            "t": "2026-04-14T14:00:00Z",
            "o": 185.50,
            "h": 186.20,
            "l": 185.10,
            "c": 186.00,
            "v": 12345,
        }
    ]
    rows = parse_bars("AAPL", bars_json)
    assert len(rows) == 1
    ticker, ts, o, h, lo, c, v = rows[0]
    assert ticker == "AAPL"
    assert ts == "2026-04-14T14:00:00Z"
    assert o == 185.50
    assert h == 186.20
    assert lo == 185.10
    assert c == 186.00
    assert v == 12345


def test_parse_bars_multiple() -> None:
    """Multiple bars produce multiple rows."""
    bars_json: list[dict[str, object]] = [
        {"t": "2026-04-14T14:00:00Z", "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5, "v": 100},
        {"t": "2026-04-14T14:01:00Z", "o": 100.5, "h": 102.0, "l": 100.0, "c": 101.5, "v": 200},
    ]
    rows = parse_bars("NVDA", bars_json)
    assert len(rows) == 2
    assert rows[0][0] == "NVDA"
    assert rows[1][0] == "NVDA"


def test_parse_bars_skips_empty_timestamp() -> None:
    """Bars without a timestamp are skipped."""
    bars_json: list[dict[str, object]] = [
        {"t": "", "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5, "v": 100},
    ]
    rows = parse_bars("TSM", bars_json)
    assert rows == []


def test_parse_bars_handles_missing_fields() -> None:
    """Missing fields default to 0."""
    bars_json: list[dict[str, object]] = [
        {"t": "2026-04-14T14:00:00Z"},
    ]
    rows = parse_bars("AAPL", bars_json)
    assert len(rows) == 1
    _, _, o, h, lo, c, v = rows[0]
    assert o == 0.0
    assert h == 0.0
    assert lo == 0.0
    assert c == 0.0
    assert v == 0


def test_parse_bars_empty_list() -> None:
    """Empty bar list produces empty result."""
    rows = parse_bars("AAPL", [])
    assert rows == []
