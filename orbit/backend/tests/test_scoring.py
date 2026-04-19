"""Comprehensive tests for the ORBIT scoring engine.

Covers:
- correlation.py: relevance clamping, recency decay monotonicity, aggregate
- verdict.py: threshold boundary tests for ACT / WAIT / IGNORE
- wilson.py: CI math verified against known values
- outcome_tracker.py: directional correctness evaluation
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from app.config import Settings
from app.db import get_db, run_migrations
from app.schemas import DirectionEnum, VerdictClass
from app.scoring.correlation import (
    aggregate_relevance,
    confidence_multiplier,
    exposure_weight,
    recency_decay,
    relevance,
)
from app.scoring.outcome_tracker import track_outcomes
from app.scoring.verdict import (
    compute_verdict,
    direction_from_goldstein,
)
from app.scoring.wilson import WilsonResult, format_wilson, wilson_ci

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """Return a temporary database file path."""
    return str(tmp_path / "test_scoring.db")


# ===================================================================
# correlation.py — relevance always in [0, 1]
# ===================================================================


class TestRelevanceBounds:
    """Property: relevance(...) always returns a value in [0, 1]."""

    @pytest.mark.parametrize(
        "location, ticker, goldstein, hours, sources",
        [
            # normal cases
            ("US", "AAPL", 5.0, 0.0, 10),
            ("CN", "NVDA", -10.0, 0.0, 15),
            ("TW", "TSM", 10.0, 0.0, 1),
            # extreme goldstein
            ("US", "AAPL", 10.0, 0.0, 10),
            ("US", "AAPL", -10.0, 0.0, 10),
            # zero goldstein
            ("US", "AAPL", 0.0, 12.0, 5),
            # very old event
            ("US", "AAPL", 8.0, 1000.0, 10),
            # unknown location
            ("XX", "AAPL", 5.0, 1.0, 5),
            # unknown ticker
            ("US", "ZZZZ", 5.0, 1.0, 5),
            # zero hours
            ("TW", "TSM", 10.0, 0.0, 10),
            # boundary sources
            ("US", "AAPL", 5.0, 0.0, 0),
            ("US", "AAPL", 5.0, 0.0, 1),
            ("US", "AAPL", 5.0, 0.0, 2),
            ("US", "AAPL", 5.0, 0.0, 5),
            ("US", "AAPL", 5.0, 0.0, 10),
            ("US", "AAPL", 5.0, 0.0, 100),
        ],
    )
    def test_relevance_in_unit_interval(
        self,
        location: str,
        ticker: str,
        goldstein: float,
        hours: float,
        sources: int,
    ) -> None:
        score = relevance(location, ticker, goldstein, hours, sources)
        assert 0.0 <= score <= 1.0, f"relevance={score} out of [0,1]"


class TestRelevanceValues:
    """Spot-check specific relevance calculations."""

    def test_max_relevance_aapl_us(self) -> None:
        """AAPL, US, goldstein=10, hours=0, 10 sources -> 0.43."""
        score = relevance("US", "AAPL", 10.0, 0.0, 10)
        assert abs(score - 0.43) < 1e-6

    def test_unknown_location_is_zero(self) -> None:
        score = relevance("XX", "AAPL", 10.0, 0.0, 10)
        assert score == 0.0

    def test_zero_goldstein_is_zero(self) -> None:
        score = relevance("US", "AAPL", 0.0, 0.0, 10)
        assert score == 0.0


# ===================================================================
# correlation.py — recency decay monotonically decreasing
# ===================================================================


class TestRecencyDecay:
    """Property: recency_decay is monotonically decreasing with hours."""

    def test_monotonically_decreasing(self) -> None:
        hours_list = [0.0, 1.0, 6.0, 12.0, 24.0, 48.0, 72.0, 168.0]
        decays = [recency_decay(h) for h in hours_list]
        for i in range(len(decays) - 1):
            assert decays[i] > decays[i + 1], (
                f"decay({hours_list[i]})={decays[i]} "
                f"should be > decay({hours_list[i + 1]})={decays[i + 1]}"
            )

    def test_decay_at_zero_is_one(self) -> None:
        assert recency_decay(0.0) == 1.0

    def test_decay_at_24_is_exp_neg1(self) -> None:
        import math

        assert abs(recency_decay(24.0) - math.exp(-1.0)) < 1e-10


# ===================================================================
# correlation.py — confidence_multiplier
# ===================================================================


class TestConfidenceMultiplier:
    @pytest.mark.parametrize(
        "n, expected",
        [
            (0, 0.5),
            (1, 0.5),
            (2, 0.75),
            (4, 0.75),
            (5, 0.9),
            (9, 0.9),
            (10, 1.0),
            (100, 1.0),
        ],
    )
    def test_confidence_multiplier_values(self, n: int, expected: float) -> None:
        assert confidence_multiplier(n) == expected


# ===================================================================
# correlation.py — exposure_weight
# ===================================================================


class TestExposureWeight:
    def test_known_weight(self) -> None:
        assert exposure_weight("US", "AAPL") == 0.43

    def test_unknown_country(self) -> None:
        assert exposure_weight("BR", "AAPL") == 0.0

    def test_unknown_ticker(self) -> None:
        assert exposure_weight("US", "ZZZZ") == 0.0


# ===================================================================
# correlation.py — aggregate_relevance
# ===================================================================


class TestAggregateRelevance:
    def test_empty_list(self) -> None:
        assert aggregate_relevance([]) == 0.0

    def test_single_value(self) -> None:
        assert aggregate_relevance([0.5]) == 0.5

    def test_top3_capped_at_one(self) -> None:
        result = aggregate_relevance([0.8, 0.7, 0.6])
        assert result == 1.0  # sum=2.1 -> capped to 1.0

    def test_max_single_vs_top3(self) -> None:
        # max_single=0.9, top3=0.9+0.05+0.05=1.0
        result = aggregate_relevance([0.9, 0.05, 0.05])
        assert result == 1.0

    def test_small_values_sum(self) -> None:
        result = aggregate_relevance([0.1, 0.1, 0.1])
        assert abs(result - 0.3) < 1e-10

    def test_result_always_in_unit_interval(self) -> None:
        result = aggregate_relevance([0.2, 0.3, 0.4, 0.5])
        assert 0.0 <= result <= 1.0


# ===================================================================
# verdict.py — direction from goldstein
# ===================================================================


class TestDirectionFromGoldstein:
    def test_negative_is_short(self) -> None:
        assert direction_from_goldstein(-5.0) == DirectionEnum.SHORT

    def test_positive_is_long(self) -> None:
        assert direction_from_goldstein(5.0) == DirectionEnum.LONG

    def test_near_zero_is_flat(self) -> None:
        assert direction_from_goldstein(0.0) == DirectionEnum.FLAT
        assert direction_from_goldstein(0.5) == DirectionEnum.FLAT
        assert direction_from_goldstein(-0.9) == DirectionEnum.FLAT

    def test_boundary_at_one(self) -> None:
        # abs(1.0) is exactly at threshold — treated as LONG
        assert direction_from_goldstein(1.0) == DirectionEnum.LONG
        assert direction_from_goldstein(-1.0) == DirectionEnum.SHORT


# ===================================================================
# verdict.py — threshold boundaries
# ===================================================================


class TestVerdictThresholds:
    """Test exact boundary conditions for ACT / WAIT / IGNORE."""

    def test_act_verdict(self) -> None:
        """score=0.55, hit_rate >= 0.54, contradicting <= 1 -> ACT (BUY)."""
        v = compute_verdict(
            ticker="AAPL",
            aggregated_score=0.55,
            goldstein_score=5.0,
            contradicting_count=0,
            has_active_position=False,
        )
        assert v.verdict_object["label"] == "ACT"
        assert v.verdict_class == VerdictClass.BUY
        assert v.direction == DirectionEnum.LONG

    def test_act_verdict_short(self) -> None:
        """ACT + negative goldstein -> SELL."""
        v = compute_verdict(
            ticker="AAPL",
            aggregated_score=0.60,
            goldstein_score=-5.0,
            contradicting_count=1,
            has_active_position=False,
        )
        assert v.verdict_object["label"] == "ACT"
        assert v.verdict_class == VerdictClass.SELL
        assert v.direction == DirectionEnum.SHORT

    def test_wait_score_boundary(self) -> None:
        """score=0.30 (lower boundary of WAIT range) -> WAIT."""
        v = compute_verdict(
            ticker="AAPL",
            aggregated_score=0.30,
            goldstein_score=5.0,
            contradicting_count=0,
            has_active_position=False,
        )
        assert v.verdict_object["label"] == "WAIT"

    def test_wait_just_below_act(self) -> None:
        """score=0.549 -> WAIT (just below ACT threshold)."""
        v = compute_verdict(
            ticker="AAPL",
            aggregated_score=0.549,
            goldstein_score=5.0,
            contradicting_count=0,
            has_active_position=False,
        )
        assert v.verdict_object["label"] == "WAIT"

    def test_wait_from_contradicting(self) -> None:
        """Even with high score, contradicting >= 2 -> WAIT."""
        v = compute_verdict(
            ticker="AAPL",
            aggregated_score=0.80,
            goldstein_score=5.0,
            contradicting_count=2,
            has_active_position=False,
        )
        assert v.verdict_object["label"] == "WAIT"

    def test_wait_from_flat_direction(self) -> None:
        """Near-zero goldstein -> FLAT direction -> WAIT."""
        v = compute_verdict(
            ticker="AAPL",
            aggregated_score=0.60,
            goldstein_score=0.0,
            contradicting_count=0,
            has_active_position=False,
        )
        assert v.verdict_object["label"] == "WAIT"
        assert v.direction == DirectionEnum.FLAT

    def test_ignore_low_score_no_position(self) -> None:
        """score < 0.30 AND no active position -> IGNORE."""
        v = compute_verdict(
            ticker="AAPL",
            aggregated_score=0.20,
            goldstein_score=5.0,
            contradicting_count=0,
            has_active_position=False,
        )
        assert v.verdict_object["label"] == "IGNORE"

    def test_low_score_with_position_is_wait(self) -> None:
        """score < 0.30 but active position -> WAIT (not IGNORE)."""
        v = compute_verdict(
            ticker="AAPL",
            aggregated_score=0.20,
            goldstein_score=5.0,
            contradicting_count=0,
            has_active_position=True,
        )
        assert v.verdict_object["label"] == "WAIT"

    def test_verdict_contains_metadata(self) -> None:
        """Verdict object includes hit_rate, contradicting_count, and enrichment fields."""
        v = compute_verdict(
            ticker="TSM",
            aggregated_score=0.70,
            goldstein_score=-3.0,
            contradicting_count=0,
            has_active_position=False,
            top_event="taiwan escalation",
            top_score=0.68,
            exposure_code="TW",
            exposure_weight_pct=0.55,
        )
        assert "hit_rate" in v.verdict_object
        assert "contradicting_count" in v.verdict_object
        assert v.verdict_object["contradicting_count"] == "0"
        assert v.verdict_object["top_event"] == "taiwan escalation"
        assert v.verdict_object["top_score"] == "0.68"
        assert v.verdict_object["exposure_code"] == "TW"
        assert v.verdict_object["exposure_weight"] == "55%"
        assert v.verdict_object["n_analogs"] == "76"
        assert v.verdict_object["hit_rate"] == "58.3%"


# ===================================================================
# wilson.py — CI math verified against known values
# ===================================================================


class TestWilsonCI:
    def test_known_value_50_percent(self) -> None:
        """50/100 trials: verify against hand-computed Wilson CI."""
        result = wilson_ci(50, 100)
        # z=1.96, p=0.5, n=100
        # center = (0.5 + 1.96^2/(2*100)) / (1 + 1.96^2/100)
        #        = (0.5 + 0.019208) / (1 + 0.038416)
        #        = 0.519208 / 1.038416 = 0.50000...
        assert abs(result.center - 0.5) < 0.01
        assert result.lower is not None
        assert result.upper is not None
        # Symmetric around 0.5
        assert abs((result.upper - result.center) - (result.center - result.lower)) < 1e-6
        # Width should be roughly 0.192
        width = result.upper - result.lower
        assert 0.18 < width < 0.20

    def test_known_value_80_percent(self) -> None:
        """80/100 trials."""
        result = wilson_ci(80, 100)
        assert result.lower is not None
        assert result.upper is not None
        assert 0.70 < result.lower < 0.75
        assert 0.83 < result.upper < 0.87

    def test_small_sample_returns_none(self) -> None:
        """n <= 20 -> lower and upper are None."""
        result = wilson_ci(10, 20)
        assert result.lower is None
        assert result.upper is None
        assert result.n == 20
        assert result.center > 0

    def test_n_zero(self) -> None:
        result = wilson_ci(0, 0)
        assert result.center == 0.0
        assert result.lower is None
        assert result.upper is None
        assert result.n == 0

    def test_n_21_returns_bounds(self) -> None:
        """n=21 is just above threshold — should have bounds."""
        result = wilson_ci(11, 21)
        assert result.lower is not None
        assert result.upper is not None

    def test_perfect_score(self) -> None:
        """100/100 — center near 1.0, lower > 0.95."""
        result = wilson_ci(100, 100)
        assert result.lower is not None
        assert result.upper is not None
        assert result.center > 0.95
        assert result.lower > 0.95

    def test_zero_successes(self) -> None:
        """0/100 — center near 0, upper < 0.05."""
        result = wilson_ci(0, 100)
        assert result.lower is not None
        assert result.upper is not None
        assert result.center < 0.05
        assert result.upper < 0.05

    def test_lower_less_than_upper(self) -> None:
        """Lower bound always < upper bound when bounds exist."""
        for s in range(0, 101, 10):
            result = wilson_ci(s, 100)
            if result.lower is not None and result.upper is not None:
                assert result.lower < result.upper


class TestFormatWilson:
    def test_early_sample(self) -> None:
        result = WilsonResult(center=0.5, lower=None, upper=None, n=10)
        assert format_wilson(result) == "n=10 (early sample)"

    def test_full_format(self) -> None:
        result = WilsonResult(center=0.5, lower=0.4, upper=0.6, n=100)
        s = format_wilson(result)
        assert "0.500" in s
        assert "0.400" in s
        assert "0.600" in s
        assert "n=100" in s


# ===================================================================
# outcome_tracker.py — directional correctness
# ===================================================================


class TestOutcomeTracker:
    async def test_track_outcomes_empty_db(self, tmp_db_path: str) -> None:
        """No trades -> zero outcomes written."""
        await run_migrations(tmp_db_path)
        settings = Settings(database_url=tmp_db_path)
        written = await track_outcomes(settings)
        assert written == 0

    async def test_track_outcomes_long_correct(self, tmp_db_path: str) -> None:
        """Closed long trade with positive return -> directionally correct."""
        await run_migrations(tmp_db_path)
        async with get_db(tmp_db_path) as conn:
            await _insert_test_trade(
                conn,
                trade_id="t1",
                verdict_id="v1",
                ticker="AAPL",
                direction="long",
                entry_price=100.0,
                exit_price=110.0,
            )

        settings = Settings(database_url=tmp_db_path)
        written = await track_outcomes(settings)
        assert written == 1

        async with get_db(tmp_db_path) as conn:
            cursor = await conn.execute(
                "SELECT forward_return, directionally_correct FROM outcomes WHERE trade_id = ?",
                ("t1",),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert abs(row[0] - 0.1) < 1e-4  # 10% return
            assert row[1] == 1  # correct

    async def test_track_outcomes_long_incorrect(self, tmp_db_path: str) -> None:
        """Closed long trade with negative return -> directionally incorrect."""
        await run_migrations(tmp_db_path)
        async with get_db(tmp_db_path) as conn:
            await _insert_test_trade(
                conn,
                trade_id="t2",
                verdict_id="v2",
                ticker="AAPL",
                direction="long",
                entry_price=100.0,
                exit_price=90.0,
            )

        settings = Settings(database_url=tmp_db_path)
        written = await track_outcomes(settings)
        assert written == 1

        async with get_db(tmp_db_path) as conn:
            cursor = await conn.execute(
                "SELECT forward_return, directionally_correct FROM outcomes WHERE trade_id = ?",
                ("t2",),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert abs(row[0] - (-0.1)) < 1e-4
            assert row[1] == 0  # incorrect

    async def test_track_outcomes_short_correct(self, tmp_db_path: str) -> None:
        """Closed short trade with negative return -> directionally correct."""
        await run_migrations(tmp_db_path)
        async with get_db(tmp_db_path) as conn:
            await _insert_test_trade(
                conn,
                trade_id="t3",
                verdict_id="v3",
                ticker="NVDA",
                direction="short",
                entry_price=200.0,
                exit_price=180.0,
            )

        settings = Settings(database_url=tmp_db_path)
        written = await track_outcomes(settings)
        assert written == 1

        async with get_db(tmp_db_path) as conn:
            cursor = await conn.execute(
                "SELECT directionally_correct FROM outcomes WHERE trade_id = ?",
                ("t3",),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 1

    async def test_track_outcomes_flat_always_incorrect(self, tmp_db_path: str) -> None:
        """Flat direction is never directionally correct."""
        await run_migrations(tmp_db_path)
        async with get_db(tmp_db_path) as conn:
            await _insert_test_trade(
                conn,
                trade_id="t4",
                verdict_id="v4",
                ticker="TSM",
                direction="flat",
                entry_price=100.0,
                exit_price=110.0,
            )

        settings = Settings(database_url=tmp_db_path)
        written = await track_outcomes(settings)
        assert written == 1

        async with get_db(tmp_db_path) as conn:
            cursor = await conn.execute(
                "SELECT directionally_correct FROM outcomes WHERE trade_id = ?",
                ("t4",),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 0  # flat is never correct

    async def test_track_outcomes_idempotent(self, tmp_db_path: str) -> None:
        """Running twice does not duplicate outcomes."""
        await run_migrations(tmp_db_path)
        async with get_db(tmp_db_path) as conn:
            await _insert_test_trade(
                conn,
                trade_id="t5",
                verdict_id="v5",
                ticker="AAPL",
                direction="long",
                entry_price=100.0,
                exit_price=120.0,
            )

        settings = Settings(database_url=tmp_db_path)
        assert await track_outcomes(settings) == 1
        assert await track_outcomes(settings) == 0  # already tracked

    async def test_open_trade_skipped(self, tmp_db_path: str) -> None:
        """Trade without exit_price is not evaluated."""
        await run_migrations(tmp_db_path)
        async with get_db(tmp_db_path) as conn:
            # Insert event
            await conn.execute(
                "INSERT INTO events (id, source, timestamp, description) VALUES (?, ?, ?, ?)",
                ("e1", "test", "2025-01-01T00:00:00Z", "Test event"),
            )
            # Insert verdict
            await conn.execute(
                """INSERT INTO verdicts
                    (id, ticker, verdict_class, direction, relevance_score, issued_at, verdict_object)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("v6", "AAPL", "buy", "long", 0.6, "2025-01-01T00:00:00Z", '{"label":"ACT"}'),
            )
            # Insert open trade (no exit_price)
            await conn.execute(
                """INSERT INTO trades
                    (id, verdict_id, ticker, direction, size_shares, entry_price, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("t6", "v6", "AAPL", "long", 10, 100.0, "2025-01-01T00:00:00Z"),
            )
            await conn.commit()

        settings = Settings(database_url=tmp_db_path)
        assert await track_outcomes(settings) == 0


# ===================================================================
# Helpers for outcome tracker tests
# ===================================================================


async def _insert_test_trade(
    conn: aiosqlite.Connection,
    trade_id: str,
    verdict_id: str,
    ticker: str,
    direction: str,
    entry_price: float,
    exit_price: float,
) -> None:
    """Insert a complete event -> event_score -> verdict -> trade chain."""
    event_id = f"evt-{trade_id}"
    # Event
    await conn.execute(
        "INSERT INTO events (id, source, timestamp, description) VALUES (?, ?, ?, ?)",
        (event_id, "test", "2025-01-01T00:00:00Z", "Test event"),
    )
    # Event score
    await conn.execute(
        """INSERT INTO event_scores (event_id, ticker, relevance, implied_direction)
        VALUES (?, ?, ?, ?)""",
        (event_id, ticker, 0.7, direction),
    )
    # Verdict
    await conn.execute(
        """INSERT INTO verdicts
            (id, ticker, verdict_class, direction, relevance_score, issued_at, verdict_object)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (verdict_id, ticker, "buy", direction, 0.7, "2025-01-01T00:00:00Z", '{"label":"ACT"}'),
    )
    # Closed trade
    await conn.execute(
        """INSERT INTO trades
            (id, verdict_id, ticker, direction, size_shares,
             entry_price, exit_price, executed_at, closed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            trade_id,
            verdict_id,
            ticker,
            direction,
            10,
            entry_price,
            exit_price,
            "2025-01-01T00:00:00Z",
            "2025-01-02T00:00:00Z",
        ),
    )
    await conn.commit()
