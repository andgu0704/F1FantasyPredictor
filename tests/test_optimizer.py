"""Optimizer invariants — pure unit tests on synthetic picks (no DB)."""

from __future__ import annotations

import pytest

from f1fantasy.optimizer import PENALTY_PER_TRANSFER, optimize_lineup
from f1fantasy.predictor.base import Pick


def _pool():
    """8 drivers + 4 constructors with clear value ordering."""
    drivers = [Pick("driver", f"d{i}", f"Driver{i}", price=5 + i, expected_points=10 + 2 * i)
               for i in range(8)]
    cons = [Pick("constructor", f"c{i}", f"Team{i}", price=10 + i, expected_points=20 + 3 * i)
            for i in range(4)]
    return drivers + cons


def test_fills_exact_roster_within_budget():
    lineup = optimize_lineup(_pool(), budget=100.0)
    assert len(lineup.drivers) == 5
    assert len(lineup.constructors) == 2
    assert lineup.total_price <= 100.0 + 1e-6
    assert lineup.boosted is not None  # DRS goes to one driver


def test_tighter_budget_lowers_spend():
    cheap = optimize_lineup(_pool(), budget=60.0)
    assert cheap.total_price <= 60.0 + 1e-6


def test_drs_boost_doubles_one_driver():
    lineup = optimize_lineup(_pool(), budget=100.0, drs_multiplier=2)
    base = sum(p.expected_points for p in lineup.drivers + lineup.constructors)
    assert lineup.gross_points == pytest.approx(base + lineup.boosted.expected_points)


def test_extra_drs_triples_boost():
    two = optimize_lineup(_pool(), budget=100.0, drs_multiplier=2)
    three = optimize_lineup(_pool(), budget=100.0, drs_multiplier=3)
    # Tripling adds one more copy of the (same best) boosted driver's points.
    assert three.gross_points == pytest.approx(two.gross_points + two.boosted.expected_points)


def test_transfer_penalty_applied_beyond_free_allowance():
    pool = _pool()
    # A current team made of the cheapest/worst picks forces transfers.
    current = {"d0", "d1", "d2", "d3", "d4", "c0", "c1"}
    lineup = optimize_lineup(pool, budget=100.0, current_team=current, free_transfers=2)
    extra = max(0, lineup.num_transfers - 2)
    assert lineup.penalty == pytest.approx(PENALTY_PER_TRANSFER * extra)
    assert lineup.net_points == pytest.approx(lineup.gross_points - lineup.penalty)


def test_wildcard_waives_penalty():
    pool = _pool()
    current = {"d0", "d1", "d2", "d3", "d4", "c0", "c1"}
    normal = optimize_lineup(pool, budget=100.0, current_team=current, free_transfers=0)
    wild = optimize_lineup(pool, budget=100.0, current_team=current, free_transfers=0,
                           unlimited_transfers=True)
    assert wild.penalty == 0.0
    assert wild.net_points >= normal.net_points


def test_unlimited_budget_can_exceed_cap():
    rich = optimize_lineup(_pool(), budget=100.0, unlimited_budget=True)
    # Limitless should pick the most expensive (highest-points) entities freely.
    assert rich.gross_points >= optimize_lineup(_pool(), budget=100.0).gross_points


def test_raises_when_pool_too_small():
    with pytest.raises(ValueError):
        optimize_lineup([Pick("driver", "d0", "D0", 5, 10)], budget=100.0)
