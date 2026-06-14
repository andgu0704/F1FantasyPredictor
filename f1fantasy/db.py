"""SQLite storage layer.

The schema is deliberately normalized around the two things the optimizer
ultimately needs per Grand Prix: a points history (to predict expected points)
and current fantasy prices. Everything else is supporting context.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "f1fantasy.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS drivers (
    driver_id    TEXT PRIMARY KEY,
    code         TEXT,
    permanent_no INTEGER,
    given_name   TEXT,
    family_name  TEXT,
    nationality  TEXT
);

CREATE TABLE IF NOT EXISTS constructors (
    constructor_id TEXT PRIMARY KEY,
    name           TEXT,
    nationality    TEXT
);

CREATE TABLE IF NOT EXISTS races (
    season    INTEGER NOT NULL,
    round     INTEGER NOT NULL,
    race_name TEXT,
    circuit_id   TEXT,
    circuit_name TEXT,
    date      TEXT,
    is_sprint INTEGER DEFAULT 0,      -- 1 if the weekend has a sprint race
    PRIMARY KEY (season, round)
);

-- Sprint race results (same shape as `results`; sprint weekends only).
CREATE TABLE IF NOT EXISTS sprint_results (
    season         INTEGER NOT NULL,
    round          INTEGER NOT NULL,
    driver_id      TEXT NOT NULL,
    constructor_id TEXT NOT NULL,
    grid           INTEGER,
    position       INTEGER,
    position_text  TEXT,
    points         REAL,
    status         TEXT,
    PRIMARY KEY (season, round, driver_id)
);

-- One row per driver per race (race result).
CREATE TABLE IF NOT EXISTS results (
    season         INTEGER NOT NULL,
    round          INTEGER NOT NULL,
    driver_id      TEXT NOT NULL,
    constructor_id TEXT NOT NULL,
    grid           INTEGER,
    position       INTEGER,           -- NULL if DNF/DNS
    position_text  TEXT,              -- "R", "D", "1", ... preserves the raw status
    points         REAL,              -- championship points (NOT fantasy points)
    laps           INTEGER,
    status         TEXT,              -- "Finished", "+1 Lap", "Accident", ...
    fastest_lap_rank INTEGER,         -- 1 == fastest lap of the race
    PRIMARY KEY (season, round, driver_id),
    FOREIGN KEY (season, round) REFERENCES races(season, round),
    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id),
    FOREIGN KEY (constructor_id) REFERENCES constructors(constructor_id)
);

-- One row per driver per race (qualifying result).
CREATE TABLE IF NOT EXISTS qualifying (
    season         INTEGER NOT NULL,
    round          INTEGER NOT NULL,
    driver_id      TEXT NOT NULL,
    constructor_id TEXT NOT NULL,
    position       INTEGER,
    q1_ms          INTEGER,           -- lap times stored as milliseconds, NULL if no time
    q2_ms          INTEGER,
    q3_ms          INTEGER,
    PRIMARY KEY (season, round, driver_id),
    FOREIGN KEY (season, round) REFERENCES races(season, round)
);

-- Fantasy market snapshot, captured per gameday (prices + season-to-date
-- fantasy stats float week to week). Sourced from the official F1 Fantasy
-- statistics feeds. `fantasy_id` is the game's own player/team id; the link
-- to Jolpica driver_id/constructor_id is held in fantasy_entity_map.
CREATE TABLE IF NOT EXISTS fantasy_stats (
    season       INTEGER NOT NULL,
    gameday      INTEGER NOT NULL,    -- F1 Fantasy GamedayId (the upcoming race week)
    entity_type  TEXT NOT NULL,       -- 'driver' | 'constructor'
    fantasy_id   TEXT NOT NULL,       -- the game's playerid / teamid
    name         TEXT,
    team_name    TEXT,
    price        REAL,                -- current price in $M (curvalue)
    f_points     REAL,                -- season-to-date total fantasy points
    f_avg        REAL,                -- average fantasy points per race
    points_per_million REAL,          -- value efficiency
    price_change REAL,                -- price delta over the season
    captured_at  TEXT NOT NULL,       -- ISO timestamp of the snapshot
    PRIMARY KEY (season, gameday, entity_type, fantasy_id)
);

-- Live game parameters for a gameday (budget cap, deadline).
CREATE TABLE IF NOT EXISTS game_state (
    season         INTEGER NOT NULL,
    gameday        INTEGER NOT NULL,
    max_team_value REAL,              -- budget cap in $M
    deadline       TEXT,
    captured_at    TEXT NOT NULL,
    PRIMARY KEY (season, gameday)
);

-- Median green-flag race-pace gap (seconds) to the fastest car, per driver per
-- race, from FastF1 timing. Captures true race pace, which is less noisy than
-- finishing position. Used causally (prior races) as a predictor feature.
CREATE TABLE IF NOT EXISTS race_pace (
    season     INTEGER NOT NULL,
    round      INTEGER NOT NULL,
    driver_id  TEXT NOT NULL,
    pace_gap_s REAL,
    PRIMARY KEY (season, round, driver_id)
);

-- Maps a fantasy player/team id to a Jolpica driver_id/constructor_id so the
-- price/points data can be joined to historical results. Populated in Phase 2.
CREATE TABLE IF NOT EXISTS fantasy_entity_map (
    entity_type TEXT NOT NULL,        -- 'driver' | 'constructor'
    fantasy_id  TEXT NOT NULL,
    jolpica_id  TEXT NOT NULL,        -- driver_id or constructor_id
    PRIMARY KEY (entity_type, fantasy_id)
);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open a connection, creating the parent dir and schema if needed."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
