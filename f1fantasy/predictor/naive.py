"""Naive predictor: expected points = season average so far (`f_avg`).

This is the Phase 2 baseline that proves the predictor->optimizer contract. It
ignores form, track, and reliability — Phase 3's heuristic replaces it behind
the same interface.
"""

from __future__ import annotations

import sqlite3

from f1fantasy.predictor.base import Pick, PredictorBase
from f1fantasy.risk import driver_points_std


class NaivePredictor(PredictorBase):
    name = "naive-season-average"

    def predict(self, conn: sqlite3.Connection, season: int, gameday: int) -> list[Pick]:
        rows = conn.execute(
            """SELECT fs.entity_type, fs.fantasy_id, fs.name, fs.team_name,
                      fs.price, fs.f_avg, fs.f_points, m.jolpica_id
               FROM fantasy_stats fs
               LEFT JOIN fantasy_entity_map m
                 ON m.entity_type = fs.entity_type AND m.fantasy_id = fs.fantasy_id
               WHERE fs.season = ? AND fs.gameday = ? AND fs.price IS NOT NULL""",
            (season, gameday),
        ).fetchall()

        picks: list[Pick] = []
        for r in rows:
            # Fall back to a per-race share of season points if f_avg is missing.
            expected = r["f_avg"]
            if expected is None:
                expected = (r["f_points"] or 0.0) / max(gameday - 1, 1)
            expected = float(expected)
            std = (driver_points_std(conn, season, r["jolpica_id"], expected)
                   if r["jolpica_id"] and r["entity_type"] == "driver" else 0.0)
            label = r["name"] or r["team_name"]
            picks.append(
                Pick(r["entity_type"], r["fantasy_id"], label, float(r["price"]), expected, std)
            )
        return picks
