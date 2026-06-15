"""Produce a recommended lineup for the current gameday.

Pulls the live budget/gameday from game_state, runs the configured predictor to
get expected points, and solves the optimizer. This is the seam the web API
(Phase 4) will call.

    uv run python -m f1fantasy.recommend
"""

from __future__ import annotations

import sqlite3

from f1fantasy.db import connect
from f1fantasy.optimizer import DEFAULT_BUDGET, Lineup, optimize_lineup
from f1fantasy.predictor.base import PredictorBase
from f1fantasy.predictor.naive import NaivePredictor


def current_gameday(conn: sqlite3.Connection) -> tuple[int, int, float]:
    row = conn.execute(
        "SELECT season, gameday, max_team_value FROM game_state ORDER BY captured_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise RuntimeError("No game_state captured yet — run the ingestion first.")
    season, gd, budget = row["season"], row["gameday"], row["max_team_value"] or DEFAULT_BUDGET

    # If results exist for this gameday, advance to the next one for picking.
    latest_race = conn.execute(
        "SELECT MAX(round) r FROM results WHERE season=?", (season,)
    ).fetchone()["r"]
    if latest_race and latest_race >= gd:
        gd = latest_race + 1

    return season, gd, budget


def recommend(
    conn: sqlite3.Connection,
    predictor: PredictorBase | None = None,
    drs_boost: bool = True,
) -> tuple[Lineup, str]:
    predictor = predictor or NaivePredictor()
    season, gameday, budget = current_gameday(conn)
    picks = predictor.predict(conn, season, gameday)
    lineup = optimize_lineup(picks, budget=budget, drs_boost=drs_boost)
    header = (
        f"Gameday {gameday} ({season})  |  budget ${budget:.0f}M  |  "
        f"predictor: {predictor.name}"
    )
    return lineup, header


if __name__ == "__main__":
    conn = connect()
    lineup, header = recommend(conn)
    print(header)
    print("-" * len(header))
    print(lineup.pretty())
