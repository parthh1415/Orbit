"""ORBIT flight routes — semiconductor supply chain flight corridors."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import TRACKED_TICKERS, get_settings
from app.ingest.flights import get_flight_routes
from app.schemas import FlightRoute

router = APIRouter(prefix="/api/flights", tags=["flights"])


@router.get("", response_model=list[FlightRoute])
async def list_flights() -> list[FlightRoute]:
    """Return all synthetic flight corridors."""
    settings = get_settings()
    return await get_flight_routes(settings)


@router.get("/{ticker}", response_model=list[FlightRoute])
async def get_flights_for_ticker(ticker: str) -> list[FlightRoute]:
    """Return flight corridors relevant to *ticker*."""
    if ticker not in TRACKED_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown ticker '{ticker}'. Must be one of {list(TRACKED_TICKERS)}",
        )

    settings = get_settings()
    all_routes = await get_flight_routes(settings)
    return [r for r in all_routes if r.relevance_ticker == ticker]
