"""Naive predictor: expected points = season average so far (`f_avg`).

This is the Phase 2 baseline that proves the predictor->optimizer contract. It
ignores form, track, and reliability — Phase 3's heuristic replaces it behind
the same interface.
"""

from __future__ import annotations

import sqlite3

from f1fantasy.predictor.base import Pick, PredictorBase


class NaivePredictor(PredictorBase):
    name = "naive-season-average"

    def predict(self, conn: sqlite3.Connection, season: int, gameday: int) -> list[Pick]:
        rows = conn.execute(
            """SELECT entity_type, fantasy_id, name, team_name, price, f_avg, f_points
               FROM fantasy_stats
               WHERE season = ? AND gameday = ? AND price IS NOT NULL""",
            (season, gameday),
        ).fetchall()

        picks: list[Pick] = []
        for r in rows:
            # Fall back to a per-race share of season points if f_avg is missing.
            expected = r["f_avg"]
            if expected is None:
                expected = (r["f_points"] or 0.0) / max(gameday - 1, 1)
            label = r["name"] or r["team_name"]
            picks.append(
                Pick(r["entity_type"], r["fantasy_id"], label, float(r["price"]), float(expected))
            )
        return picks
