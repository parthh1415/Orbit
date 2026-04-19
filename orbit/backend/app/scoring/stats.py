"""ORBIT statistical functions — Bayesian hit rate, Kelly sizing, EWMA stress."""

from __future__ import annotations

import math


def bayesian_hit_rate(
    wins: int,
    losses: int,
    recent_wins: int,
    recent_losses: int,
    recency_weight: float = 2.0,
) -> dict[str, float]:
    """Bayesian posterior hit rate with recency weighting."""
    eff_alpha = 1.0 + wins + recent_wins * recency_weight
    eff_beta = 1.0 + losses + recent_losses * recency_weight
    mean = eff_alpha / (eff_alpha + eff_beta)
    n = eff_alpha + eff_beta
    var = (eff_alpha * eff_beta) / (n * n * (n + 1))
    std = math.sqrt(var) if var > 0 else 0.0
    lower = max(0.0, mean - 1.96 * std)
    upper = min(1.0, mean + 1.96 * std)
    recent_total = max(1, recent_wins + recent_losses)
    eff_hit = 0.6 * (recent_wins / recent_total) + 0.4 * mean
    return {
        "mean": round(mean, 4),
        "lower_95": round(lower, 4),
        "upper_95": round(upper, 4),
        "effective_hit_rate": round(eff_hit, 4),
    }


def kelly_position_size(
    hit_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    available_capital: float,
    price: float,
    half_kelly: bool = True,
) -> dict[str, float | int]:
    """Kelly criterion position sizing."""
    if avg_loss_pct == 0 or avg_win_pct == 0:
        return {
            "kelly_fraction": 0.0,
            "recommended_dollars": 0.0,
            "recommended_shares": 0,
            "price": price,
        }
    win_loss_ratio = avg_win_pct / avg_loss_pct
    f = hit_rate - (1 - hit_rate) / win_loss_ratio
    if f <= 0:
        return {
            "kelly_fraction": 0.0,
            "recommended_dollars": 0.0,
            "recommended_shares": 0,
            "price": price,
        }
    if half_kelly:
        f = f / 2
    f = max(0.05, min(0.25, f))
    dollars = f * available_capital
    shares = int(dollars / price) if price > 0 else 0
    return {
        "kelly_fraction": round(f, 4),
        "recommended_dollars": round(dollars, 2),
        "recommended_shares": shares,
        "price": price,
    }


def ewma_stress(
    event_scores: list[float],
    decay: float = 0.90,
) -> dict[str, float | bool]:
    """EWMA stress indicator over event relevance scores."""
    if len(event_scores) < 2:
        return {
            "current_stress": 0.0,
            "previous_stress": 0.0,
            "stress_delta": 0.0,
            "is_escalating": False,
        }
    s = event_scores[0]
    prev = s
    for i in range(1, len(event_scores)):
        prev = s
        s = decay * s + (1 - decay) * event_scores[i]
    delta = s - prev
    return {
        "current_stress": round(s, 4),
        "previous_stress": round(prev, 4),
        "stress_delta": round(delta, 4),
        "is_escalating": delta > 0.02,
    }
