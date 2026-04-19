"""ORBIT verdict routes — compute live verdicts for tracked tickers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

import aiosqlite
from fastapi import APIRouter, HTTPException

from app.config import TRACKED_TICKERS
from app.db import get_db
from app.ingest.gdelt import build_gdelt_description
from app.schemas import VerdictObject
from app.scoring.correlation import (
    aggregate_relevance,
    exposure_weight,
    relevance,
)
from app.scoring.verdict import compute_verdict

_BAD_DESCRIPTION_RE = re.compile(
    r"^(GDELT event \S+|https?://)",
)

router = APIRouter(prefix="/api/verdict", tags=["verdict"])


def _best_exposure(countries: list[str], ticker: str) -> tuple[str, float]:
    """Return the country code and weight with highest exposure for *ticker*."""
    best_code = ""
    best_weight = 0.0
    for code in countries:
        w = exposure_weight(code, ticker)
        if w > best_weight:
            best_weight = w
            best_code = code
    return best_code, best_weight


@router.get("/{ticker}", response_model=VerdictObject)
async def get_verdict(ticker: str) -> VerdictObject:
    """Compute and return the current verdict for *ticker*.

    Workflow
    --------
    1. Fetch events scored for this ticker from the last 24 hours.
    2. Re-score each event using ``scoring.correlation.relevance``.
    3. Aggregate and pass to ``scoring.verdict.compute_verdict``.
    """
    if ticker not in TRACKED_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown ticker '{ticker}'. Must be one of {list(TRACKED_TICKERS)}",
        )

    now = datetime.now(tz=UTC)
    cutoff = (now - timedelta(hours=24)).isoformat()

    async with get_db() as conn:
        # Fetch the TOP 20 events by pre-computed relevance score so that
        # high-volume replay ingestion (100K+ rows) does not drown the
        # signal with noise.  Uses ``computed_at`` so replay events whose
        # rebased timestamp has aged out still surface.
        cursor: aiosqlite.Cursor = await conn.execute(
            """
            SELECT e.id, e.goldstein_score, e.num_sources, e.timestamp,
                   e.countries, es.implied_direction, e.description,
                   e.cameo_code
            FROM events e
            JOIN event_scores es ON e.id = es.event_id
            WHERE es.ticker = ?
              AND es.computed_at >= ?
            ORDER BY es.relevance DESC
            LIMIT 20
            """,
            (ticker, cutoff),
        )
        rows = await cursor.fetchall()

        # Check for active position
        pos_cursor: aiosqlite.Cursor = await conn.execute(
            "SELECT COUNT(*) FROM trades WHERE ticker = ? AND exit_price IS NULL",
            (ticker,),
        )
        pos_row = await pos_cursor.fetchone()
        has_active = (int(pos_row[0]) > 0) if pos_row else False

    # Re-compute relevance scores for each event
    relevances: list[float] = []
    goldstein_scores: list[float] = []
    direction_counts: dict[str, int] = {"long": 0, "short": 0, "flat": 0}

    # Track the top event by relevance
    top_relevance = 0.0
    top_description = ""
    top_exposure_code = ""
    top_exposure_wt = 0.0

    for row in rows:
        gs = float(row[1])
        n_src = int(row[2])
        ts_str = str(row[3])
        countries_str = str(row[4]) if row[4] else "[]"
        impl_dir = str(row[5]) if row[5] else "flat"
        description = str(row[6]) if row[6] else ""
        cameo_code = str(row[7]) if row[7] else ""

        evt_time = datetime.fromisoformat(ts_str)
        if evt_time.tzinfo is None:
            evt_time = evt_time.replace(tzinfo=UTC)
        hours_since = max(0.0, (now - evt_time).total_seconds() / 3600.0)

        try:
            countries_list: list[str] = json.loads(countries_str)
        except (json.JSONDecodeError, TypeError):
            countries_list = []

        # If the stored description is a URL or raw event ID, rebuild it
        # from the country/cameo fields.
        if not description or _BAD_DESCRIPTION_RE.match(description):
            rebuilt = build_gdelt_description(
                actor1=countries_list[0] if countries_list else "",
                actor2=countries_list[1] if len(countries_list) > 1 else "",
                cameo_code=cameo_code,
                geo_fullname="",
            )
            if rebuilt:
                description = rebuilt

        # Find the best matching country for this ticker's exposure
        location, loc_weight = _best_exposure(countries_list, ticker)

        score = relevance(
            location=location,
            ticker=ticker,
            goldstein_score=gs,
            hours_since_event=hours_since,
            num_sources=n_src,
        )
        relevances.append(score)
        goldstein_scores.append(gs)
        direction_counts[impl_dir] = direction_counts.get(impl_dir, 0) + 1

        # Track highest-relevance event
        if score > top_relevance:
            top_relevance = score
            top_description = description
            top_exposure_code = location
            top_exposure_wt = loc_weight

    # Aggregate
    agg_score = aggregate_relevance(relevances) if relevances else 0.0

    # Determine dominant direction and contradictions using RATIO, not absolute
    # count. With 20 real GDELT events, 8 contradicting is normal noise (40%).
    # Only flag as contradicting if the minority direction is >45% of total.
    long_count = direction_counts.get("long", 0)
    short_count = direction_counts.get("short", 0)
    total_directional = long_count + short_count
    if total_directional > 0:
        minority = min(long_count, short_count)
        contradicting_ratio = minority / total_directional
        # Only count as contradicting if minority is >45% (genuinely mixed)
        contradicting = minority if contradicting_ratio > 0.45 else 0
    else:
        contradicting = 0

    # Use the MAJORITY direction's average goldstein (not all events averaged)
    # to prevent opposing events from canceling the signal to near-zero
    if long_count > short_count:
        majority_goldsteins = [g for g in goldstein_scores if g > 0]
    elif short_count > long_count:
        majority_goldsteins = [g for g in goldstein_scores if g < 0]
    else:
        majority_goldsteins = goldstein_scores
    avg_goldstein = (
        sum(majority_goldsteins) / len(majority_goldsteins)
        if majority_goldsteins
        else (sum(goldstein_scores) / len(goldstein_scores) if goldstein_scores else 0.0)
    )

    return compute_verdict(
        ticker=ticker,
        aggregated_score=round(agg_score, 2),
        goldstein_score=round(avg_goldstein, 2),
        contradicting_count=contradicting,
        has_active_position=has_active,
        top_event=top_description,
        top_score=top_relevance,
        exposure_code=top_exposure_code,
        exposure_weight_pct=top_exposure_wt,
    )
