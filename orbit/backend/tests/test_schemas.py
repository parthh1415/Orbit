"""Tests for app.schemas — Pydantic v2 model validation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas import (
    Bar,
    CommandRequest,
    CommandResponse,
    DirectionEnum,
    ExecuteRequest,
    ExecuteResponse,
    OutcomeRecord,
    PortSnapshot,
    Position,
    ScorecardRow,
    ScoredEvent,
    StatusMessage,
    Trade,
    VerdictClass,
    VerdictObject,
)

NOW = datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


def test_direction_enum_values() -> None:
    assert set(DirectionEnum) == {
        DirectionEnum.LONG,
        DirectionEnum.SHORT,
        DirectionEnum.FLAT,
    }


def test_verdict_class_values() -> None:
    assert len(VerdictClass) == 5


# ---------------------------------------------------------------------------
# ScoredEvent
# ---------------------------------------------------------------------------


def test_scored_event_minimal() -> None:
    ev = ScoredEvent(
        id="e1",
        source="newsapi",
        timestamp=NOW,
        description="Test event",
    )
    assert ev.id == "e1"
    assert ev.countries == []
    assert ev.implied_direction == DirectionEnum.FLAT
    assert ev.computed_at is None


def test_scored_event_full() -> None:
    ev = ScoredEvent(
        id="e2",
        source="gdelt",
        timestamp=NOW,
        description="Full event",
        cameo_code="0211",
        goldstein_score=3.4,
        num_sources=5,
        lat=34.0,
        lon=-118.0,
        countries=["US", "CN"],
        sentiment=0.75,
        metadata={"key": "val"},
        ticker="AAPL",
        relevance=0.9,
        implied_direction=DirectionEnum.LONG,
        computed_at=NOW,
    )
    assert ev.countries == ["US", "CN"]
    assert ev.ticker == "AAPL"


def test_scored_event_frozen() -> None:
    ev = ScoredEvent(id="e1", source="s", timestamp=NOW, description="d")
    with pytest.raises(ValidationError):
        ev.id = "e2"


# ---------------------------------------------------------------------------
# VerdictObject
# ---------------------------------------------------------------------------


def test_verdict_object() -> None:
    v = VerdictObject(id="v1", ticker="NVDA", issued_at=NOW)
    assert v.verdict_class == VerdictClass.HOLD
    assert v.direction == DirectionEnum.FLAT
    assert v.verdict_object == {}


# ---------------------------------------------------------------------------
# Trade
# ---------------------------------------------------------------------------


def test_trade_open() -> None:
    t = Trade(
        id="t1",
        verdict_id="v1",
        ticker="TSM",
        direction=DirectionEnum.LONG,
        size_shares=100,
        entry_price=95.0,
        executed_at=NOW,
    )
    assert t.exit_price is None
    assert t.closed_at is None
    assert t.realized_pnl is None


def test_trade_closed() -> None:
    t = Trade(
        id="t2",
        verdict_id="v1",
        ticker="TSM",
        direction=DirectionEnum.SHORT,
        size_shares=50,
        entry_price=100.0,
        exit_price=90.0,
        executed_at=NOW,
        closed_at=NOW,
        realized_pnl=500.0,
    )
    assert t.realized_pnl == 500.0


# ---------------------------------------------------------------------------
# OutcomeRecord
# ---------------------------------------------------------------------------


def test_outcome_record() -> None:
    o = OutcomeRecord(
        event_id="e1",
        verdict_id="v1",
        trade_id="t1",
        horizon="1d",
        forward_return=0.02,
        directionally_correct=True,
        computed_at=NOW,
    )
    assert o.directionally_correct is True


# ---------------------------------------------------------------------------
# Bar
# ---------------------------------------------------------------------------


def test_bar() -> None:
    b = Bar(
        ticker="AAPL",
        timestamp=NOW,
        open=150.0,
        high=155.0,
        low=149.0,
        close=153.0,
        volume=1000000,
    )
    assert b.close == 153.0


# ---------------------------------------------------------------------------
# PortSnapshot
# ---------------------------------------------------------------------------


def test_port_snapshot() -> None:
    p = PortSnapshot(
        location="Shanghai",
        lat=31.2,
        lon=121.5,
        ship_count=42,
        timestamp=NOW,
    )
    assert p.ship_count == 42


# ---------------------------------------------------------------------------
# ScorecardRow
# ---------------------------------------------------------------------------


def test_scorecard_row() -> None:
    row = ScorecardRow(
        ticker="AAPL",
        total_trades=10,
        wins=7,
        losses=3,
        win_rate=0.7,
        avg_return=0.015,
        sharpe=1.5,
    )
    assert row.win_rate == 0.7


# ---------------------------------------------------------------------------
# StatusMessage
# ---------------------------------------------------------------------------


def test_status_message() -> None:
    sm = StatusMessage(level="info", message="System online", timestamp=NOW)
    assert sm.level == "info"


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


def test_position() -> None:
    pos = Position(
        ticker="NVDA",
        direction=DirectionEnum.LONG,
        size_shares=200,
        entry_price=800.0,
        current_price=850.0,
        unrealized_pnl=10000.0,
    )
    assert pos.unrealized_pnl == 10000.0


# ---------------------------------------------------------------------------
# Execute request / response
# ---------------------------------------------------------------------------


def test_execute_request() -> None:
    req = ExecuteRequest(
        ticker="AAPL",
        direction=DirectionEnum.LONG,
        size_shares=10,
    )
    assert req.ticker == "AAPL"


def test_execute_response() -> None:
    resp = ExecuteResponse(success=True, trade_id="t1", message="ok")
    assert resp.success is True


# ---------------------------------------------------------------------------
# Command request / response
# ---------------------------------------------------------------------------


def test_command_request() -> None:
    req = CommandRequest(command="status")
    assert req.command == "status"


def test_command_response() -> None:
    resp = CommandResponse(success=True, output="all good")
    assert resp.output == "all good"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_invalid_direction_rejected() -> None:
    with pytest.raises(ValidationError):
        ExecuteRequest(
            ticker="AAPL",
            direction="up",  # type: ignore[arg-type]
            size_shares=10,
        )
