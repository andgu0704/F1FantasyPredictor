"""Sprint-weekend awareness.

On a sprint weekend drivers score fantasy points in the sprint *and* the Grand
Prix, so more points are on the table and the optimal team can shift toward
strong sprint performers. The base predictors estimate a normal race; this layer
adds a per-driver estimate of the extra sprint-race points when the upcoming
round is a sprint weekend.

Honest scope: the official F1 Fantasy sprint scoring (positions, overtakes,
fastest lap, driver-of-the-day) isn't published per driver, so we approximate
the sprint contribution from each driver's recent sprint finishing positions.
It's a heuristic uplift, not a calibrated score — enough to tilt the lineup and
the DRS pick toward drivers who deliver in sprints.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace

from f1fantasy.predictor.base import Pick

SPRINT_RECENT = 6   # most recent sprint results to average over

# Rough fantasy points by sprint finishing position (win heavy, scoring zone
# tapering, any classified finish small-positive, DNF small-negative).
_SPRINT_POINTS = {1: 10.0, 2: 8.0, 3: 7.0, 4: 6.0, 5: 5.0, 6: 4.0, 7: 3.0, 8: 2.0}


def upcoming_is_sprint(conn: sqlite3.Connection, season: int) -> bool:
    """Is the next (unraced) round a sprint weekend?"""
    row = conn.execute(
        """SELECT is_sprint FROM races WHERE season=? AND round=(
               SELECT COALESCE(MAX(round), 0) + 1 FROM results WHERE season=?)""",
        (season, season),
    ).fetchone()
    return bool(row["is_sprint"]) if row else False


def _sprint_points(position: int | None) -> float:
    if position is None or position < 1:
        return -5.0                       # DNF: fantasy sprint score tends negative
    return _SPRINT_POINTS.get(position, 1.0)  # P9+ classified ~ +1


def sprint_uplift(conn: sqlite3.Connection, season: int, driver_id: str) -> float:
    """Estimated extra fantasy points from the sprint, from recent sprint form."""
    rows = conn.execute(
        "SELECT position FROM sprint_results WHERE driver_id=? "
        "ORDER BY season DESC, round DESC LIMIT ?",
        (driver_id, SPRINT_RECENT),
    ).fetchall()
    if not rows:
        return 0.0
    return sum(_sprint_points(r["position"]) for r in rows) / len(rows)


def _driver_id(conn: sqlite3.Connection, fantasy_id: str) -> str | None:
    row = conn.execute(
        "SELECT jolpica_id FROM fantasy_entity_map WHERE entity_type='driver' AND fantasy_id=?",
        (fantasy_id,),
    ).fetchone()
    return row["jolpica_id"] if row else None


def sprint_adjusted(conn: sqlite3.Connection, season: int, picks: list[Pick]) -> list[Pick]:
    """Add the sprint uplift to driver picks when the next round is a sprint.

    A no-op on normal weekends, so it is always safe to wrap a predictor's output.
    """
    if not upcoming_is_sprint(conn, season):
        return picks
    out: list[Pick] = []
    for p in picks:
        if p.entity_type != "driver":
            out.append(p)
            continue
        did = _driver_id(conn, p.fantasy_id)
        uplift = sprint_uplift(conn, season, did) if did else 0.0
        out.append(replace(p, expected_points=p.expected_points + uplift) if uplift else p)
    return out
