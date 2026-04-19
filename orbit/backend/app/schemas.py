"""ORBIT Pydantic v2 models — mirrors every SQLite table and API contract."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DirectionEnum(StrEnum):
    """Trade / verdict direction."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class VerdictClass(StrEnum):
    """Verdict classification bucket."""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


# ---------------------------------------------------------------------------
# Domain models (match SQLite tables)
# ---------------------------------------------------------------------------


class ScoredEvent(BaseModel):
    """Combines the *events* and *event_scores* tables."""

    model_config = ConfigDict(strict=True, frozen=True)

    # -- events columns --
    id: str
    source: str
    timestamp: datetime
    description: str
    cameo_code: str = ""
    goldstein_score: float = 0.0
    num_sources: int = 1
    lat: float = 0.0
    lon: float = 0.0
    countries: list[str] = Field(default_factory=list)
    sentiment: float = 0.0
    metadata: dict[str, str] = Field(default_factory=dict)

    # -- event_scores columns --
    ticker: str = ""
    relevance: float = 0.0
    implied_direction: DirectionEnum = DirectionEnum.FLAT
    computed_at: datetime | None = None


class VerdictObject(BaseModel):
    """Matches the *verdicts* table."""

    model_config = ConfigDict(strict=True, frozen=True)

    id: str
    ticker: str
    verdict_class: VerdictClass = VerdictClass.HOLD
    direction: DirectionEnum = DirectionEnum.FLAT
    relevance_score: float = 0.0
    issued_at: datetime
    verdict_object: dict[str, str] = Field(default_factory=dict)


class Trade(BaseModel):
    """Matches the *trades* table."""

    model_config = ConfigDict(strict=True, frozen=True)

    id: str
    verdict_id: str
    ticker: str
    direction: DirectionEnum
    size_shares: int
    entry_price: float
    exit_price: float | None = None
    executed_at: datetime
    closed_at: datetime | None = None
    realized_pnl: float | None = None


class OutcomeRecord(BaseModel):
    """Matches the *outcomes* table."""

    model_config = ConfigDict(strict=True, frozen=True)

    event_id: str
    verdict_id: str
    trade_id: str
    horizon: str
    forward_return: float
    directionally_correct: bool
    computed_at: datetime


class Bar(BaseModel):
    """Matches the *bars* table (OHLCV data)."""

    model_config = ConfigDict(strict=True, frozen=True)

    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class PortSnapshot(BaseModel):
    """Matches the *port_snapshots* table."""

    model_config = ConfigDict(strict=True, frozen=True)

    location: str
    lat: float
    lon: float
    ship_count: int
    timestamp: datetime


class FlightRoute(BaseModel):
    """A synthetic flight corridor in the semiconductor supply chain."""

    model_config = ConfigDict(strict=True, frozen=True)

    id: str
    origin: str
    origin_lat: float
    origin_lon: float
    destination: str
    dest_lat: float
    dest_lon: float
    cargo_type: str  # "semiconductor", "components", "finished_goods"
    frequency: str  # "daily", "weekly"
    relevance_ticker: str  # which tracked ticker this route matters for
    active: bool


# ---------------------------------------------------------------------------
# Scorecard / dashboard helpers
# ---------------------------------------------------------------------------


class ScorecardRow(BaseModel):
    """One row in the back-test / live scorecard."""

    model_config = ConfigDict(strict=True, frozen=True)

    ticker: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_return: float
    sharpe: float


class StatusMessage(BaseModel):
    """System-status payload pushed over WebSocket."""

    model_config = ConfigDict(strict=True, frozen=True)

    level: str  # "info" | "warn" | "error"
    message: str
    timestamp: datetime


class Position(BaseModel):
    """Open-position summary for the dashboard."""

    model_config = ConfigDict(strict=True, frozen=True)

    ticker: str
    direction: DirectionEnum
    size_shares: int
    entry_price: float
    current_price: float
    unrealized_pnl: float


class PortfolioSummary(BaseModel):
    """Aggregate portfolio statistics for the dashboard."""

    model_config = ConfigDict(strict=True, frozen=True)

    capital_total: float
    capital_deployed: float
    capital_available: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    open_positions: int
    closed_positions: int


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ExecuteRequest(BaseModel):
    """Body of POST /api/execute."""

    model_config = ConfigDict(strict=True, frozen=True)

    ticker: str
    direction: DirectionEnum
    size_shares: int


class ExecuteResponse(BaseModel):
    """Response from POST /api/execute."""

    model_config = ConfigDict(strict=True, frozen=True)

    success: bool
    trade_id: str
    message: str


class CommandRequest(BaseModel):
    """Body of POST /api/command."""

    model_config = ConfigDict(strict=True, frozen=True)

    command: str


class CommandResponse(BaseModel):
    """Response from POST /api/command."""

    model_config = ConfigDict(strict=True, frozen=True)

    success: bool
    output: str
