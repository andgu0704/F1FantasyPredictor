"""Lineup optimizer.

Picks the F1 Fantasy roster that maximizes expected fantasy points subject to
the official constraints, as an integer linear program (PuLP / CBC):

    maximize   sum_i  points_i * pick_i  +  sum_d points_d * boost_d
    subject to sum_i price_i * pick_i <= budget
               sum over drivers      pick_i == n_drivers
               sum over constructors pick_i == n_constructors
               sum_d boost_d == 1            (DRS boost goes to exactly one driver)
               boost_d <= pick_d             (and only to a picked driver)

The DRS Boost doubles one driver's score, so a boosted driver contributes its
points twice; the ILP chooses both the roster and which driver to boost jointly,
which can change the optimal roster (a slightly pricier driver may be worth it
once boosted). Set drs_boost=False to ignore the chip.
"""

from __future__ import annotations

from dataclasses import dataclass

import pulp

from f1fantasy.predictor.base import Pick

# Official F1 Fantasy roster rules.
N_DRIVERS = 5
N_CONSTRUCTORS = 2
DEFAULT_BUDGET = 100.0


@dataclass
class Lineup:
    drivers: list[Pick]
    constructors: list[Pick]
    boosted: Pick | None          # driver receiving the 2x DRS boost
    total_price: float
    expected_points: float        # includes the boost bonus

    def pretty(self) -> str:
        lines = [
            f"Expected points: {self.expected_points:.1f}   "
            f"Spend: ${self.total_price:.1f}M",
            "Drivers:",
        ]
        for d in sorted(self.drivers, key=lambda p: p.expected_points, reverse=True):
            tag = "  << DRS 2x" if self.boosted and d.fantasy_id == self.boosted.fantasy_id else ""
            lines.append(f"  {d.name:22} ${d.price:>5.1f}M  {d.expected_points:>6.1f} pts{tag}")
        lines.append("Constructors:")
        for c in sorted(self.constructors, key=lambda p: p.expected_points, reverse=True):
            lines.append(f"  {c.name:22} ${c.price:>5.1f}M  {c.expected_points:>6.1f} pts")
        return "\n".join(lines)


def optimize_lineup(
    picks: list[Pick],
    budget: float = DEFAULT_BUDGET,
    n_drivers: int = N_DRIVERS,
    n_constructors: int = N_CONSTRUCTORS,
    drs_boost: bool = True,
) -> Lineup:
    drivers = [p for p in picks if p.entity_type == "driver"]
    constructors = [p for p in picks if p.entity_type == "constructor"]
    if len(drivers) < n_drivers or len(constructors) < n_constructors:
        raise ValueError("Not enough drivers/constructors in the pool to fill a lineup.")

    prob = pulp.LpProblem("f1_fantasy", pulp.LpMaximize)

    pick = {p.fantasy_id: pulp.LpVariable(f"pick_{p.entity_type}_{p.fantasy_id}", cat="Binary")
            for p in picks}
    boost = {d.fantasy_id: pulp.LpVariable(f"boost_{d.fantasy_id}", cat="Binary")
             for d in drivers} if drs_boost else {}

    # Objective: base points for every pick, plus one extra copy for the boosted driver.
    objective = pulp.lpSum(p.expected_points * pick[p.fantasy_id] for p in picks)
    if drs_boost:
        objective += pulp.lpSum(d.expected_points * boost[d.fantasy_id] for d in drivers)
    prob += objective

    # Budget and roster-size constraints.
    prob += pulp.lpSum(p.price * pick[p.fantasy_id] for p in picks) <= budget
    prob += pulp.lpSum(pick[d.fantasy_id] for d in drivers) == n_drivers
    prob += pulp.lpSum(pick[c.fantasy_id] for c in constructors) == n_constructors

    if drs_boost:
        prob += pulp.lpSum(boost.values()) == 1
        for d in drivers:
            prob += boost[d.fantasy_id] <= pick[d.fantasy_id]

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"No optimal lineup found (status: {pulp.LpStatus[status]}).")

    chosen_d = [d for d in drivers if pick[d.fantasy_id].value() > 0.5]
    chosen_c = [c for c in constructors if pick[c.fantasy_id].value() > 0.5]
    boosted = next((d for d in drivers if drs_boost and boost[d.fantasy_id].value() > 0.5), None)

    total_price = sum(p.price for p in chosen_d + chosen_c)
    total_points = sum(p.expected_points for p in chosen_d + chosen_c)
    if boosted:
        total_points += boosted.expected_points

    return Lineup(chosen_d, chosen_c, boosted, total_price, total_points)
