"""Lightweight risk / variance estimates.

Fantasy scores swing mainly with DNFs and big position changes. We approximate a
driver's points standard deviation from the dispersion of their season's
finishing "goodness", scaled into points via their average. It's a rough proxy,
not a calibrated distribution — enough to surface floor/ceiling and to give an
order-of-magnitude value for the No Negative chip.
"""

from __future__ import annotations

import math
import sqlite3
import statistics

from f1fantasy.features import goodness
from f1fantasy.predictor.base import Pick


def driver_points_std(conn: sqlite3.Connection, season: int, driver_id: str, baseline: float) -> float:
    """Std-dev of the driver's fantasy points, estimated from result dispersion."""
    positions = [r["position"] for r in conn.execute(
        "SELECT position FROM results WHERE season=? AND driver_id=?", (season, driver_id))]
    goods = [goodness(p) for p in positions]
    if len(goods) < 2:
        return 0.0
    mean_g = statistics.fmean(goods)
    if mean_g <= 0:
        return abs(baseline)  # all-DNF: downside ~ the whole (often negative) baseline
    return statistics.pstdev(goods) * (baseline / mean_g)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def no_negative_value(picks: list[Pick]) -> float:
    """Approx points recovered by the No Negative chip = Σ E[(-score)+] over
    drivers, treating each score as Normal(expected, std)."""
    total = 0.0
    for p in picks:
        if p.entity_type != "driver" or p.std <= 0:
            continue
        m, s = -p.expected_points, p.std         # distribution of the negated score
        # E[max(0, Y)] for Y ~ N(m, s).
        total += max(0.0, s * _norm_pdf(m / s) + m * _norm_cdf(m / s))
    return total
