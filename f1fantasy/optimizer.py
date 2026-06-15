"""Lineup optimizer.

Picks the F1 Fantasy roster that maximizes expected fantasy points subject to
the official constraints, as a (mixed) integer linear program (PuLP / CBC):

    maximize   sum_i points_i * pick_i  +  (drs_mult-1) * sum_d points_d * boost_d
               - PENALTY_PER_TRANSFER * extra_transfers
    subject to sum_i price_i * pick_i <= budget          (unless Limitless)
               sum over drivers      pick_i == n_drivers
               sum over constructors pick_i == n_constructors
               sum_d boost_d == 1,  boost_d <= pick_d     (DRS to one picked driver)
               extra_transfers >= (transfers in) - free_transfers,  >= 0

Transfers: when a current team is supplied, buying an entity not already owned
costs a transfer; transfers beyond the free allowance cost PENALTY_PER_TRANSFER
points each. The ILP trades the penalty against the points gain, so it never
suggests a swap that is not worth it.

Chips are expressed as flags on the same model:
    Wildcard   -> unlimited_transfers (no penalty)
    Limitless  -> unlimited_budget + unlimited_transfers (one race, all free)
    Extra DRS  -> a second 2x boost on a different driver, on top of the usual
                  boost which becomes 3x (so one driver 3x + one driver 2x)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pulp

from f1fantasy.predictor.base import Pick

# Official F1 Fantasy rules.
N_DRIVERS = 5
N_CONSTRUCTORS = 2
DEFAULT_BUDGET = 100.0
PENALTY_PER_TRANSFER = 10.0     # points lost per transfer beyond the free allowance


@dataclass
class Lineup:
    drivers: list[Pick]
    constructors: list[Pick]
    boosted: Pick | None          # driver receiving the (primary) DRS boost
    total_price: float
    gross_points: float           # expected points incl. boost, before transfer penalty
    drs_multiplier: int = 2       # multiplier on the primary boosted driver
    boosted2: Pick | None = None  # second driver boosted 2x (Extra DRS chip only)
    points_std: float = 0.0       # 1-sigma uncertainty on gross_points (risk band)

    @property
    def floor(self) -> float:
        return self.net_points - self.points_std

    @property
    def ceiling(self) -> float:
        return self.net_points + self.points_std
    transfers_in: list[Pick] = field(default_factory=list)   # newly bought
    transfers_out: list[Pick] = field(default_factory=list)  # sold (info only)
    num_transfers: int = 0
    penalty: float = 0.0

    @property
    def net_points(self) -> float:
        return self.gross_points - self.penalty

    def pretty(self) -> str:
        boost_tag = f"DRS {self.drs_multiplier}x"
        lines = [
            f"Net points: {self.net_points:.1f}  "
            f"(gross {self.gross_points:.1f} - penalty {self.penalty:.0f})   "
            f"Spend: ${self.total_price:.1f}M",
        ]
        if self.num_transfers:
            outs = ", ".join(p.name for p in self.transfers_out) or "-"
            ins = ", ".join(p.name for p in self.transfers_in) or "-"
            lines.append(f"Transfers ({self.num_transfers}): OUT {outs}  ->  IN {ins}")
        lines.append("Drivers:")
        for d in sorted(self.drivers, key=lambda p: p.expected_points, reverse=True):
            tag = f"  << {boost_tag}" if self.boosted and d.fantasy_id == self.boosted.fantasy_id else ""
            lines.append(f"  {d.name:22} ${d.price:>5.1f}M  {d.expected_points:>6.1f} pts{tag}")
        lines.append("Constructors:")
        for c in sorted(self.constructors, key=lambda p: p.expected_points, reverse=True):
            lines.append(f"  {c.name:22} ${c.price:>5.1f}M  {c.expected_points:>6.1f} pts")
        return "\n".join(lines)


def fixed_team_points(
    picks: list[Pick],
    team_ids: set[str],
    drs_boost: bool = True,
    extra_drs: bool = False,
) -> float:
    """Net points of an exact, fixed team (no transfers) with the boost applied
    to the best driver(s) — used to value a user's current team as-is."""
    chosen = [p for p in picks if p.fantasy_id in team_ids]
    gross = sum(p.expected_points for p in chosen)
    drivers = sorted((p for p in chosen if p.entity_type == "driver"),
                     key=lambda p: p.expected_points, reverse=True)
    if drs_boost and drivers:
        primary_mult = 3 if extra_drs else 2
        gross += (primary_mult - 1) * drivers[0].expected_points
        if extra_drs and len(drivers) > 1:
            gross += drivers[1].expected_points  # second driver 2x
    return gross


def optimize_lineup(
    picks: list[Pick],
    budget: float = DEFAULT_BUDGET,
    n_drivers: int = N_DRIVERS,
    n_constructors: int = N_CONSTRUCTORS,
    drs_boost: bool = True,
    drs_multiplier: int = 2,
    current_team: set[str] | None = None,
    free_transfers: int = 2,
    unlimited_transfers: bool = False,
    unlimited_budget: bool = False,
    extra_drs: bool = False,
    risk_aversion: float = 0.0,
) -> Lineup:
    # Extra DRS chip: the primary boost becomes 3x and a second driver gets 2x.
    primary_mult = 3 if extra_drs else drs_multiplier
    second_boost = extra_drs and drs_boost
    # risk_aversion > 0 prefers safer (low-variance) picks; < 0 chases upside.
    # Linear proxy: shift each pick's score by -risk_aversion * its std.
    drivers = [p for p in picks if p.entity_type == "driver"]
    constructors = [p for p in picks if p.entity_type == "constructor"]
    if len(drivers) < n_drivers or len(constructors) < n_constructors:
        raise ValueError("Not enough drivers/constructors in the pool to fill a lineup.")

    prob = pulp.LpProblem("f1_fantasy", pulp.LpMaximize)
    pick = {p.fantasy_id: pulp.LpVariable(f"pick_{p.entity_type}_{p.fantasy_id}", cat="Binary")
            for p in picks}
    boost = {d.fantasy_id: pulp.LpVariable(f"boost_{d.fantasy_id}", cat="Binary")
             for d in drivers} if drs_boost else {}
    boost2 = {d.fantasy_id: pulp.LpVariable(f"boost2_{d.fantasy_id}", cat="Binary")
              for d in drivers} if second_boost else {}

    objective = pulp.lpSum(p.expected_points * pick[p.fantasy_id] for p in picks)
    if drs_boost:
        # A boosted driver's points are multiplied by primary_mult: add the
        # (primary_mult - 1) extra copies on top of the base pick.
        objective += (primary_mult - 1) * pulp.lpSum(
            d.expected_points * boost[d.fantasy_id] for d in drivers)
    if second_boost:
        # Second driver gets a 2x boost (one extra copy of their points).
        objective += pulp.lpSum(d.expected_points * boost2[d.fantasy_id] for d in drivers)

    # Risk adjustment: nudge the score by the picks' std (same boost coefficients
    # as the points term, since a boosted driver's spread scales with the boost).
    if risk_aversion:
        risk = pulp.lpSum(p.std * pick[p.fantasy_id] for p in picks)
        if drs_boost:
            risk += (primary_mult - 1) * pulp.lpSum(d.std * boost[d.fantasy_id] for d in drivers)
        if second_boost:
            risk += pulp.lpSum(d.std * boost2[d.fantasy_id] for d in drivers)
        objective += -risk_aversion * risk

    # Transfer penalty (only when a current team is known and not waived).
    owned = current_team or set()
    if owned and not unlimited_transfers:
        bought = pulp.lpSum(pick[p.fantasy_id] for p in picks if p.fantasy_id not in owned)
        extra = pulp.LpVariable("extra_transfers", lowBound=0)
        prob += extra >= bought - free_transfers
        objective += -PENALTY_PER_TRANSFER * extra

    prob += objective

    if not unlimited_budget:
        prob += pulp.lpSum(p.price * pick[p.fantasy_id] for p in picks) <= budget
    prob += pulp.lpSum(pick[d.fantasy_id] for d in drivers) == n_drivers
    prob += pulp.lpSum(pick[c.fantasy_id] for c in constructors) == n_constructors
    if drs_boost:
        prob += pulp.lpSum(boost.values()) == 1
        for d in drivers:
            prob += boost[d.fantasy_id] <= pick[d.fantasy_id]
    if second_boost:
        prob += pulp.lpSum(boost2.values()) == 1
        for d in drivers:
            prob += boost2[d.fantasy_id] <= pick[d.fantasy_id]
            # The two boosts must land on different drivers.
            prob += boost[d.fantasy_id] + boost2[d.fantasy_id] <= 1

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"No optimal lineup found (status: {pulp.LpStatus[status]}).")

    chosen_d = [d for d in drivers if pick[d.fantasy_id].value() > 0.5]
    chosen_c = [c for c in constructors if pick[c.fantasy_id].value() > 0.5]
    chosen_ids = {p.fantasy_id for p in chosen_d + chosen_c}
    boosted = next((d for d in drivers if drs_boost and boost[d.fantasy_id].value() > 0.5), None)
    boosted2 = next((d for d in drivers if second_boost and boost2[d.fantasy_id].value() > 0.5), None)

    total_price = sum(p.price for p in chosen_d + chosen_c)
    gross = sum(p.expected_points for p in chosen_d + chosen_c)
    if boosted:
        gross += (primary_mult - 1) * boosted.expected_points
    if boosted2:
        gross += boosted2.expected_points  # 2x => one extra copy

    # Confidence band: variances add (picks assumed independent); a boosted
    # driver's std scales with its multiplier, so its variance scales with mult^2.
    def _mult(p: Pick) -> int:
        if boosted and p.fantasy_id == boosted.fantasy_id:
            return primary_mult
        if boosted2 and p.fantasy_id == boosted2.fantasy_id:
            return 2
        return 1
    variance = sum((_mult(p) * p.std) ** 2 for p in chosen_d + chosen_c)
    points_std = variance ** 0.5

    transfers_in = [p for p in chosen_d + chosen_c if p.fantasy_id not in owned] if owned else []
    transfers_out = [p for p in picks if p.fantasy_id in owned and p.fantasy_id not in chosen_ids]
    num_transfers = len(transfers_in)
    penalty = 0.0
    if owned and not unlimited_transfers:
        penalty = PENALTY_PER_TRANSFER * max(0, num_transfers - free_transfers)

    return Lineup(
        drivers=chosen_d, constructors=chosen_c, boosted=boosted, boosted2=boosted2,
        total_price=total_price, gross_points=gross, drs_multiplier=primary_mult,
        points_std=points_std,
        transfers_in=transfers_in, transfers_out=transfers_out,
        num_transfers=num_transfers, penalty=penalty,
    )
