"""Chip (booster) valuation.

Each chip is the same optimization under relaxed rules. We solve the normal
("base") problem and each chip variant, and report how many extra net points the
chip buys this race so you know whether it is worth burning a limited-use chip.

Only the chips a pre-race point-estimate model can value are optimized:
    Wildcard   unlimited free transfers
    Limitless  unlimited budget + unlimited transfers (one race)
    Extra DRS  3x boost instead of 2x

Final Fix / No Negative / Auto Pilot are surfaced by the API as available but not
valued (they depend on in-race events or score variance, not point estimates).
"""

from __future__ import annotations

from dataclasses import dataclass

from f1fantasy.optimizer import Lineup, optimize_lineup
from f1fantasy.predictor.base import Pick


@dataclass
class ChipValue:
    chip: str
    delta: float          # extra net points vs the base lineup
    lineup: Lineup


def base_lineup(
    picks: list[Pick], budget: float, current_team: set[str] | None, free_transfers: int,
) -> Lineup:
    return optimize_lineup(
        picks, budget=budget, current_team=current_team, free_transfers=free_transfers,
    )


def evaluate_chips(
    picks: list[Pick],
    budget: float,
    current_team: set[str] | None = None,
    free_transfers: int = 2,
) -> tuple[Lineup, list[ChipValue]]:
    base = base_lineup(picks, budget, current_team, free_transfers)

    variants = {
        "wildcard": dict(unlimited_transfers=True),
        "limitless": dict(unlimited_transfers=True, unlimited_budget=True),
        "extra_drs": dict(drs_multiplier=3),
    }
    chips: list[ChipValue] = []
    for name, kwargs in variants.items():
        lineup = optimize_lineup(
            picks, budget=budget, current_team=current_team,
            free_transfers=free_transfers, **kwargs,
        )
        chips.append(ChipValue(name, lineup.net_points - base.net_points, lineup))

    chips.sort(key=lambda c: c.delta, reverse=True)
    return base, chips
