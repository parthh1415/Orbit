"""ORBIT backend entry point."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import TRACKED_TICKERS, Settings, get_settings
from app.db import run_migrations
from app.execution.local_sim import execute_paper_trade
from app.routes import (
    chart,
    command,
    events,
    flights,
    portfolio,
    ports,
    scorecard,
    stats,
    status,
    verdict,
)
from app.schemas import DirectionEnum, ExecuteResponse, Trade

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demo-mode seed
# ---------------------------------------------------------------------------


async def _seed_demo(settings: Settings) -> None:
    """Run every ingest module once synchronously to populate the demo DB."""
    from app.ingest.ais import poll_ais
    from app.ingest.alpaca import poll_alpaca
    from app.ingest.demo_seed import seed_event_scores, seed_events, seed_trades_and_outcomes
    from app.ingest.flights import poll_flights
    from app.ingest.fred import poll_fred
    from app.ingest.gdelt import poll_gdelt
    from app.ingest.news import poll_news

    logger.info("ORBIT demo seed: populating database from demo_snapshot.json")
    await poll_alpaca(settings)
    await poll_gdelt(settings)
    await poll_news(settings)
    await poll_fred(settings)
    await poll_ais(settings)
    await poll_flights(settings)
    await seed_events(settings)
    await seed_event_scores(settings)
    await seed_trades_and_outcomes(settings)
    logger.info("ORBIT demo seed: complete")


# ---------------------------------------------------------------------------
# APScheduler setup (live mode only)
# ---------------------------------------------------------------------------


def _start_scheduler(settings: Settings) -> None:
    """Configure and start APScheduler background jobs for live ingestion."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()

    async def _job_alpaca() -> None:
        try:
            from app.ingest.alpaca import poll_alpaca

            await poll_alpaca(settings)
        except Exception:
            logger.exception("Scheduler: alpaca job failed")

    async def _job_gdelt() -> None:
        try:
            from app.ingest.gdelt import poll_gdelt

            await poll_gdelt(settings)
        except Exception:
            logger.exception("Scheduler: gdelt job failed")

    async def _job_news() -> None:
        try:
            from app.ingest.news import poll_news

            await poll_news(settings)
        except Exception:
            logger.exception("Scheduler: news job failed")

    async def _job_ais() -> None:
        try:
            from app.ingest.ais import poll_ais

            await poll_ais(settings)
        except Exception:
            logger.exception("Scheduler: ais job failed")

    async def _job_fred() -> None:
        try:
            from app.ingest.fred import poll_fred

            await poll_fred(settings)
        except Exception:
            logger.exception("Scheduler: fred job failed")

    async def _job_flights() -> None:
        try:
            from app.ingest.flights import poll_flights

            await poll_flights(settings)
        except Exception:
            logger.exception("Scheduler: flights job failed")

    async def _job_outcomes() -> None:
        try:
            from app.scoring.outcome_tracker import track_outcomes

            await track_outcomes(settings)
        except Exception:
            logger.exception("Scheduler: outcome tracker job failed")

    scheduler.add_job(_job_alpaca, "interval", seconds=60, id="alpaca")
    scheduler.add_job(_job_gdelt, "interval", minutes=15, id="gdelt")
    scheduler.add_job(_job_news, "interval", seconds=60, id="news")
    scheduler.add_job(_job_ais, "interval", seconds=60, id="ais")
    scheduler.add_job(_job_flights, "interval", minutes=15, id="flights")
    scheduler.add_job(_job_outcomes, "interval", seconds=60, id="outcomes")

    scheduler.start()
    logger.info("APScheduler started with 6 ingestion jobs + outcome tracker")

    # Fire FRED once at startup (via the event loop)
    asyncio.get_running_loop().create_task(_job_fred())


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run startup tasks (migrations, seed/scheduler) before serving requests."""
    settings = get_settings()
    await run_migrations()

    if settings.replay_mode:
        # Seed demo trades/positions so the dashboard has data from the start.
        # The server starts serving immediately with demo data while the
        # replay prefetch downloads GDELT/Yahoo/NewsAPI in the background.
        await _seed_demo(settings)

        async def _start_replay_background() -> None:
            from app.ingest.replay import prefetch_replay_data, start_replay

            logger.info("ORBIT replay: prefetching in background...")
            cache = await prefetch_replay_data(settings)
            logger.info("ORBIT replay: prefetch done, starting replay loop")
            await start_replay(settings, cache)

        asyncio.create_task(_start_replay_background())  # noqa: RUF006
    elif settings.demo_mode:
        await _seed_demo(settings)
    else:
        _start_scheduler(settings)

    yield


app = FastAPI(title="ORBIT", version="0.1.0", lifespan=lifespan)

# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Include route modules
# ---------------------------------------------------------------------------

app.include_router(chart.router)
app.include_router(portfolio.router)
app.include_router(events.router)
app.include_router(verdict.router)
app.include_router(scorecard.router)
app.include_router(command.router)
app.include_router(status.router)
app.include_router(ports.router)
app.include_router(stats.router)
app.include_router(flights.router)


# ---------------------------------------------------------------------------
# Trade execution endpoint
# ---------------------------------------------------------------------------


class _TradeRequest(BaseModel):
    """Non-strict request body for trade execution (allows str -> enum coercion)."""

    ticker: str
    direction: DirectionEnum
    size_shares: int


@app.post("/api/trades/execute", response_model=ExecuteResponse)
async def execute_trade(body: _TradeRequest) -> ExecuteResponse:
    """Execute a paper trade via the local simulator."""
    if body.ticker not in TRACKED_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown ticker '{body.ticker}'. Must be one of {list(TRACKED_TICKERS)}",
        )

    settings = get_settings()
    try:
        trade: Trade = await execute_paper_trade(
            ticker=body.ticker,
            direction=body.direction,
            settings=settings,
            size_shares=body.size_shares,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ExecuteResponse(
        success=True,
        trade_id=trade.id,
        message=(
            f"Paper trade executed: {trade.direction.value} {trade.size_shares} "
            f"shares of {trade.ticker} @ ${trade.entry_price:.2f}"
        ),
    )
