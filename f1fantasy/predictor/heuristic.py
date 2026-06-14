"""Heuristic predictor.

Starts from each entity's real season-average fantasy points (`f_avg`, from the
fantasy feed) and nudges it by three signals computed from Jolpica results:

  * form        - recent finishing positions vs the season so far
  * track       - history at the upcoming circuit vs the entity's overall level
  * reliability - recent DNF rate

Finishing position is turned into a "goodness" score g(pos) = GRID+1-pos (so a
win is best, a DNF is 0). Each signal becomes a bounded multiplier; their product
is the combined factor. We apply it additively around a floored scale so the
adjustment always moves expected points in the correct direction even when the
baseline is small or negative (back-markers can have negative season averages):

    expected = f_avg + (combined_factor - 1) * max(f_avg, SCALE_FLOOR)

This needs no fantasy scoring table (which the feeds don't expose) and stays in
real fantasy-point units. It is intentionally simple and tunable; an ML model
can later replace it behind the same PredictorBase interface.
"""

from __future__ import annotations

import sqlite3

from f1fantasy.predictor.base import Pick, PredictorBase
from f1fantasy.risk import driver_points_std

GRID = 20
RECENT_RACES = 3
SCALE_FLOOR = 5.0          # min points-scale an adjustment is applied over
FORM_CLAMP = (0.80, 1.20)
TRACK_CLAMP = (0.85, 1.15)
COMBINED_CLAMP = (0.60, 1.40)


def _goodness(position: int | None) -> float:
    """Map a finishing position to a 0..GRID score; DNF (NULL) -> 0."""
    if position is None or position < 1:
        return 0.0
    return float(max(GRID + 1 - position, 0))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _ratio(recent: float, baseline: float, clamp: tuple[float, float]) -> float:
    if baseline <= 0:
        return 1.0
    return _clamp(recent / baseline, *clamp)


class HeuristicPredictor(PredictorBase):
    name = "heuristic-form-track-reliability"

    def predict(self, conn: sqlite3.Connection, season: int, gameday: int) -> list[Pick]:
        circuit_id = self._upcoming_circuit(conn, season)
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
            baseline = r["f_avg"]
            if baseline is None:
                baseline = (r["f_points"] or 0.0) / max(gameday - 1, 1)
            baseline = float(baseline)

            factor = 1.0
            if r["jolpica_id"]:
                id_col = "driver_id" if r["entity_type"] == "driver" else "constructor_id"
                factor = self._entity_factor(conn, season, id_col, r["jolpica_id"], circuit_id)

            expected = baseline + (factor - 1.0) * max(baseline, SCALE_FLOOR)
            std = (driver_points_std(conn, season, r["jolpica_id"], baseline)
                   if r["jolpica_id"] and r["entity_type"] == "driver" else 0.0)
            picks.append(
                Pick(r["entity_type"], r["fantasy_id"], r["name"] or r["team_name"],
                     float(r["price"]), expected, std)
            )
        return picks

    # ------------------------------------------------------------------ helpers

    def _upcoming_circuit(self, conn: sqlite3.Connection, season: int) -> str | None:
        row = conn.execute(
            """SELECT circuit_id FROM races
               WHERE season = ? AND round = (
                   SELECT COALESCE(MAX(round), 0) + 1 FROM results WHERE season = ?)""",
            (season, season),
        ).fetchone()
        return row["circuit_id"] if row else None

    def _entity_factor(
        self, conn: sqlite3.Connection, season: int, id_col: str, id_val: str,
        circuit_id: str | None,
    ) -> float:
        # Per-race goodness this season, most recent round first.
        season_rows = conn.execute(
            f"""SELECT position FROM results
                WHERE season = ? AND {id_col} = ? ORDER BY round DESC""",
            (season, id_val),
        ).fetchall()
        if not season_rows:
            return 1.0
        season_g = [_goodness(r["position"]) for r in season_rows]

        season_avg = sum(season_g) / len(season_g)
        recent = season_g[:RECENT_RACES]
        recent_avg = sum(recent) / len(recent)
        form = _ratio(recent_avg, season_avg, FORM_CLAMP)

        # Reliability: DNF share over the recent window (position IS NULL).
        recent_rows = season_rows[:RECENT_RACES]
        dnf_rate = sum(1 for r in recent_rows if r["position"] is None) / len(recent_rows)
        reliability = 1.0 - 0.5 * dnf_rate

        # Track: goodness at this circuit (any season) vs overall goodness.
        track = 1.0
        if circuit_id:
            track_rows = conn.execute(
                f"""SELECT res.position FROM results res
                    JOIN races ra ON ra.season = res.season AND ra.round = res.round
                    WHERE ra.circuit_id = ? AND res.{id_col} = ?""",
                (circuit_id, id_val),
            ).fetchall()
            if track_rows:
                track_avg = sum(_goodness(r["position"]) for r in track_rows) / len(track_rows)
                overall_rows = conn.execute(
                    f"SELECT position FROM results WHERE {id_col} = ?", (id_val,)
                ).fetchall()
                overall_avg = sum(_goodness(r["position"]) for r in overall_rows) / len(overall_rows)
                track = _ratio(track_avg, overall_avg, TRACK_CLAMP)

        return _clamp(form * track * reliability, *COMBINED_CLAMP)
