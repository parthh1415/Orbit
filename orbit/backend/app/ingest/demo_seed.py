"""ORBIT demo seed — loads events, event_scores, verdicts, trades, and outcomes."""

from __future__ import annotations

import json
import logging
import pathlib
from datetime import UTC, datetime

from app.config import Settings
from app.db import get_db
from app.ingest._demo_time import rebase_score_timestamp

logger = logging.getLogger(__name__)

_DEMO_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "demo_snapshot.json"


def _read_snapshot() -> dict[str, object]:
    """Read and parse the demo snapshot JSON file."""
    if not _DEMO_PATH.exists():
        logger.warning("Demo snapshot not found at %s", _DEMO_PATH)
        return {}
    raw = _DEMO_PATH.read_text(encoding="utf-8")
    data: dict[str, object] = json.loads(raw)
    return data


async def seed_events(settings: Settings) -> int:
    """Load demo events from demo_snapshot.json into the database.

    Returns the number of rows written.
    """
    data = _read_snapshot()
    events = data.get("events")
    if not isinstance(events, list):
        return 0

    rows: list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]] = []
    for evt in events:
        if not isinstance(evt, dict):
            continue
        rows.append(
            (
                str(evt.get("id", "")),
                str(evt.get("source", "")),
                str(evt.get("timestamp", "")),
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

    inserted = 0
    async with get_db(settings.database_url) as db:
        for row in rows:
            try:
                await db.execute(
                    """INSERT OR IGNORE INTO events
                       (id, source, timestamp, description, cameo_code,
                        goldstein_score, num_sources, lat, lon, countries,
                        sentiment, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    row,
                )
                inserted += 1
            except Exception:
                pass
        await db.commit()

    logger.info("Demo seed: loaded %d/%d events", inserted, len(rows))
    return inserted


async def seed_event_scores(settings: Settings) -> int:
    """Load event_scores from demo_snapshot.json into the database.

    Returns the number of rows written.
    """
    data = _read_snapshot()
    scores = data.get("event_scores")
    if not isinstance(scores, list):
        return 0

    now = datetime.now(tz=UTC)
    rows: list[tuple[str, str, float, str, str]] = []
    for score in scores:
        if not isinstance(score, dict):
            continue
        event_id = str(score.get("event_id", ""))
        rows.append(
            (
                event_id,
                str(score.get("ticker", "")),
                float(score.get("relevance", 0.0)),
                str(score.get("implied_direction", "flat")),
                rebase_score_timestamp(event_id, now),
            )
        )

    if not rows:
        return 0

    inserted = 0
    async with get_db(settings.database_url) as db:
        # Insert one at a time — FK violations from missing parent events
        # are skipped silently (SQLite raises IntegrityError on FK failures
        # even with INSERT OR IGNORE).
        for row in rows:
            try:
                await db.execute(
                    """INSERT OR IGNORE INTO event_scores
                       (event_id, ticker, relevance, implied_direction, computed_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    row,
                )
                inserted += 1
            except Exception:
                pass
        await db.commit()

    logger.info("Demo seed: loaded %d/%d event_scores", inserted, len(rows))
    return inserted


async def seed_trades_and_outcomes(settings: Settings) -> int:
    """Load verdicts, trades, and outcomes from demo_snapshot.json.

    Returns the total number of rows written across all three tables.
    """
    data = _read_snapshot()
    total = 0

    # --- verdicts ---
    verdicts = data.get("verdicts")
    if isinstance(verdicts, list):
        verdict_rows: list[tuple[str, str, str, str, float, str, str]] = []
        for v in verdicts:
            if not isinstance(v, dict):
                continue
            verdict_rows.append(
                (
                    str(v.get("id", "")),
                    str(v.get("ticker", "")),
                    str(v.get("verdict_class", "hold")),
                    str(v.get("direction", "flat")),
                    float(v.get("relevance_score", 0.0)),
                    str(v.get("issued_at", datetime.now(tz=UTC).isoformat())),
                    str(v.get("verdict_object", "{}")),
                )
            )
        if verdict_rows:
            async with get_db(settings.database_url) as db:
                for row in verdict_rows:
                    try:
                        await db.execute(
                            """INSERT OR IGNORE INTO verdicts
                               (id, ticker, verdict_class, direction,
                                relevance_score, issued_at, verdict_object)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            row,
                        )
                        total += 1
                    except Exception:
                        pass
                await db.commit()
            logger.info("Demo seed: loaded verdicts (target %d)", len(verdict_rows))

    # --- trades ---
    trades = data.get("trades")
    if isinstance(trades, list):
        trade_rows: list[
            tuple[str, str, str, str, int, float, float | None, str, str | None, float | None]
        ] = []
        for t in trades:
            if not isinstance(t, dict):
                continue
            exit_price = t.get("exit_price")
            closed_at = t.get("closed_at")
            realized_pnl = t.get("realized_pnl")
            trade_rows.append(
                (
                    str(t.get("id", "")),
                    str(t.get("verdict_id", "")),
                    str(t.get("ticker", "")),
                    str(t.get("direction", "long")),
                    int(t.get("size_shares", 0)),
                    float(t.get("entry_price", 0.0)),
                    float(exit_price) if exit_price is not None else None,
                    str(t.get("executed_at", datetime.now(tz=UTC).isoformat())),
                    str(closed_at) if closed_at is not None else None,
                    float(realized_pnl) if realized_pnl is not None else None,
                )
            )
        if trade_rows:
            async with get_db(settings.database_url) as db:
                for t_row in trade_rows:
                    try:
                        await db.execute(
                            """INSERT OR IGNORE INTO trades
                               (id, verdict_id, ticker, direction, size_shares,
                                entry_price, exit_price, executed_at, closed_at, realized_pnl)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            t_row,
                        )
                        total += 1
                    except Exception:
                        pass
                await db.commit()
            logger.info("Demo seed: loaded trades (target %d)", len(trade_rows))

    # --- outcomes ---
    outcomes = data.get("outcomes")
    if isinstance(outcomes, list):
        outcome_rows: list[tuple[str, str, str, str, float, int, str]] = []
        for o in outcomes:
            if not isinstance(o, dict):
                continue
            outcome_rows.append(
                (
                    str(o.get("event_id", "")),
                    str(o.get("verdict_id", "")),
                    str(o.get("trade_id", "")),
                    str(o.get("horizon", "1d")),
                    float(o.get("forward_return", 0.0)),
                    1 if o.get("directionally_correct") else 0,
                    str(o.get("computed_at", datetime.now(tz=UTC).isoformat())),
                )
            )
        if outcome_rows:
            async with get_db(settings.database_url) as db:
                for o_row in outcome_rows:
                    try:
                        await db.execute(
                            """INSERT OR IGNORE INTO outcomes
                               (event_id, verdict_id, trade_id, horizon,
                                forward_return, directionally_correct, computed_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            o_row,
                        )
                        total += 1
                    except Exception:
                        pass
                await db.commit()
            logger.info("Demo seed: loaded outcomes (target %d)", len(outcome_rows))

    return total
