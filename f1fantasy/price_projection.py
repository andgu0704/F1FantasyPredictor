"""Projected price movement for the next gameday.

Honest scope: the official price algorithm and a historical price time-series
are not public, so this is a *heuristic direction* signal, not a precise
forecast. F1 Fantasy prices rise for entities that are good value and in form
(heavily bought) and fall for poor value. We rank entities by value efficiency
(points per $M) and recent form relative to the field and translate that into a
small projected change, capped at a realistic per-race move.

The practical use: buy projected risers *before* they rise to bank team value,
and move off projected fallers. Treat it as a tie-breaker, not gospel.
"""

from __future__ import annotations

import sqlite3
import statistics

MAX_MOVE = 0.3          # cap on projected one-race price change ($M)
VALUE_WEIGHT = 0.7      # value efficiency vs recent form blend
FORM_WEIGHT = 0.3


def _z(values: list[float]) -> dict[int, float]:
    if len(values) < 2:
        return {i: 0.0 for i in range(len(values))}
    mean = statistics.fmean(values)
    sd = statistics.pstdev(values) or 1.0
    return {i: (v - mean) / sd for i, v in enumerate(values)}


def project_prices(conn: sqlite3.Connection, season: int, gameday: int) -> dict[str, float]:
    """Return {fantasy_id: projected_price_change_$M} for the next gameday."""
    rows = conn.execute(
        """SELECT fantasy_id, points_per_million, f_avg, price
           FROM fantasy_stats
           WHERE season=? AND gameday=? AND price IS NOT NULL""",
        (season, gameday),
    ).fetchall()
    if not rows:
        return {}

    # Z-score value efficiency and recent output across the field, then blend.
    ppm = _z([r["points_per_million"] or 0.0 for r in rows])
    form = _z([(r["f_avg"] or 0.0) for r in rows])

    out: dict[str, float] = {}
    for i, r in enumerate(rows):
        score = VALUE_WEIGHT * ppm[i] + FORM_WEIGHT * form[i]
        # Map the blended z-score to a capped price move (~0.1M per z).
        out[r["fantasy_id"]] = round(max(-MAX_MOVE, min(MAX_MOVE, 0.1 * score)), 2)
    return out
