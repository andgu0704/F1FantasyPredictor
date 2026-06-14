"""Causal feature engineering from Jolpica results.

Builds one feature row per (season, round, driver) using ONLY information
available before that race (results from earlier rounds), so the same rows can
be used for training and for backtesting without leakage. The label is the
driver's "goodness" in that race (position mapped so a win is best, DNF = 0) —
a fully-available proxy for race performance that the fantasy feeds don't expose
per race.

Feature columns (see FEATURE_NAMES):
    recent_form   mean goodness over the last RECENT races this season
    season_form   mean goodness season-to-date
    reliability   1 - DNF share over the last RECENT races
    track_history mean goodness at this circuit in earlier races (any season)
    team_form     constructor's mean championship points season-to-date
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

GRID = 20
RECENT = 3
DEFAULT_GAP_S = 1.5     # fallback qualifying gap-to-pole (s) when no quali history
FEATURE_NAMES = ["recent_form", "season_form", "reliability", "track_history",
                 "team_form", "quali_pace"]


def goodness(position: int | None) -> float:
    if position is None or position < 1:
        return 0.0
    return float(max(GRID + 1 - position, 0))


@dataclass
class Row:
    season: int
    round: int
    driver_id: str
    features: list[float]
    label: float


def _load(conn: sqlite3.Connection) -> tuple[list[dict], dict]:
    results = [dict(r) for r in conn.execute(
        """SELECT res.season, res.round, res.driver_id, res.constructor_id,
                  res.position, res.points, ra.circuit_id, ra.date
           FROM results res JOIN races ra
             ON ra.season = res.season AND ra.round = res.round
           ORDER BY ra.date, res.round"""
    )]
    # Chronological index for "earlier than this race" comparisons.
    unique = {(r["season"], r["round"]): r["date"] for r in results}
    order = {sr: i for i, (sr, _date) in enumerate(
        sorted(unique.items(), key=lambda kv: (kv[1], kv[0]))
    )}

    # Qualifying gap-to-pole (seconds) per (season, round, driver): a cleaner
    # measure of pace than finishing position. best lap = fastest of Q1/Q2/Q3.
    quali = conn.execute(
        """SELECT season, round, driver_id,
                  MIN(COALESCE(q1_ms, 9e18), COALESCE(q2_ms, 9e18), COALESCE(q3_ms, 9e18)) AS best_ms
           FROM qualifying"""
    ).fetchall()
    best = {(r["season"], r["round"], r["driver_id"]): r["best_ms"]
            for r in quali if r["best_ms"] and r["best_ms"] < 9e18}
    pole = {}
    for (s, rd, _d), ms in best.items():
        pole[(s, rd)] = min(ms, pole.get((s, rd), ms))
    gap = {k: (ms - pole[(k[0], k[1])]) / 1000.0 for k, ms in best.items()}

    for r in results:
        r["quali_gap"] = gap.get((r["season"], r["round"], r["driver_id"]))
    return results, order


class _Index:
    """In-memory groupings of results for causal feature lookups."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.results, self.order = _load(conn)
        self.by_driver: dict[str, list[dict]] = {}
        self.by_circuit_driver: dict[tuple[str, str], list[dict]] = {}
        self.by_constructor_season: dict[tuple[str, int], list[dict]] = {}
        for r in self.results:
            self.by_driver.setdefault(r["driver_id"], []).append(r)
            self.by_circuit_driver.setdefault((r["circuit_id"], r["driver_id"]), []).append(r)
            self.by_constructor_season.setdefault((r["constructor_id"], r["season"]), []).append(r)

    def features_for(
        self, season: int, key: int, driver_id: str, constructor_id: str, circuit_id: str | None,
    ) -> tuple[list[float], float] | None:
        """Feature vector + season_form baseline for a race at chronological
        position `key`, using only earlier races. None if no prior history."""
        prior = [x for x in self.by_driver.get(driver_id, [])
                 if x["season"] == season and self.order[(x["season"], x["round"])] < key]
        if not prior:
            return None
        prior.sort(key=lambda x: self.order[(x["season"], x["round"])], reverse=True)

        recent = prior[:RECENT]
        recent_form = sum(goodness(x["position"]) for x in recent) / len(recent)
        season_form = sum(goodness(x["position"]) for x in prior) / len(prior)
        reliability = 1.0 - sum(1 for x in recent if x["position"] is None) / len(recent)

        track_prior = [x for x in self.by_circuit_driver.get((circuit_id, driver_id), [])
                       if self.order[(x["season"], x["round"])] < key]
        track_history = (sum(goodness(x["position"]) for x in track_prior) / len(track_prior)
                         if track_prior else season_form)

        team_prior = [x for x in self.by_constructor_season.get((constructor_id, season), [])
                      if self.order[(x["season"], x["round"])] < key]
        team_form = (sum((x["points"] or 0.0) for x in team_prior) / len(team_prior)
                     if team_prior else 0.0)

        # Recent qualifying pace: average gap-to-pole over recent prior races
        # (lower = faster). Less noisy than finishing position.
        gaps = [x["quali_gap"] for x in recent if x.get("quali_gap") is not None]
        quali_pace = sum(gaps) / len(gaps) if gaps else DEFAULT_GAP_S

        return ([recent_form, season_form, reliability, track_history, team_form, quali_pace],
                season_form)


def build_rows(conn: sqlite3.Connection) -> list[Row]:
    idx = _Index(conn)
    rows: list[Row] = []
    for r in idx.results:
        key = idx.order[(r["season"], r["round"])]
        feats = idx.features_for(r["season"], key, r["driver_id"], r["constructor_id"], r["circuit_id"])
        if feats is None:
            continue
        rows.append(Row(r["season"], r["round"], r["driver_id"], feats[0], goodness(r["position"])))
    return rows


def upcoming_features(conn: sqlite3.Connection, season: int) -> dict[str, tuple[list[float], float]]:
    """Features for the next (unraced) round, per driver currently on the grid.

    Returns {driver_id: (feature_vector, season_form_baseline)}.
    """
    idx = _Index(conn)
    next_round = (max((r["round"] for r in idx.results if r["season"] == season), default=0) + 1)
    circuit = conn.execute(
        "SELECT circuit_id FROM races WHERE season=? AND round=?", (season, next_round)
    ).fetchone()
    circuit_id = circuit["circuit_id"] if circuit else None
    key = max(idx.order.values(), default=-1) + 1  # chronologically after all results

    out: dict[str, tuple[list[float], float]] = {}
    for driver_id, recs in idx.by_driver.items():
        season_recs = [x for x in recs if x["season"] == season]
        if not season_recs:
            continue
        constructor_id = max(season_recs, key=lambda x: idx.order[(x["season"], x["round"])])["constructor_id"]
        feats = idx.features_for(season, key, driver_id, constructor_id, circuit_id)
        if feats is not None:
            out[driver_id] = feats
    return out
