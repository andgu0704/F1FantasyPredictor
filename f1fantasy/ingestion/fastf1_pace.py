"""Ingest median race-pace from FastF1 into the race_pace table.

For each race we take green-flag, non-pit, accurate laps, compute each driver's
median lap time, and store the gap (seconds) to the fastest median. This is the
one signal results-based data does not contain: actual race pace, separated from
crashes/strategy/DNFs. Drivers are matched via their 3-letter code.

    uv run python -m f1fantasy.ingestion.fastf1_pace 2025 2026

FastF1 downloads each session once and caches it under data/fastf1_cache, so the
first run is slow but subsequent runs are fast. Sessions that fail to load
(missing data) are skipped.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.getLogger("fastf1").setLevel(logging.ERROR)

import fastf1  # noqa: E402

from f1fantasy.db import connect  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "fastf1_cache"


def _code_map(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["code"]: r["driver_id"]
            for r in conn.execute("SELECT code, driver_id FROM drivers WHERE code IS NOT NULL")}


def ingest_round(conn: sqlite3.Connection, season: int, rnd: int, codes: dict[str, str]) -> int:
    session = fastf1.get_session(season, rnd, "R")
    session.load(laps=True, telemetry=False, weather=False, messages=False)
    laps = session.laps.pick_wo_box().pick_accurate()
    median = laps.groupby("Driver")["LapTime"].median().dropna()
    if median.empty:
        return 0
    secs = median.dt.total_seconds()
    best = secs.min()

    n = 0
    for code, t in secs.items():
        driver_id = codes.get(code)
        if not driver_id:
            continue
        conn.execute(
            """INSERT INTO race_pace (season, round, driver_id, pace_gap_s)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(season, round, driver_id) DO UPDATE SET pace_gap_s=excluded.pace_gap_s""",
            (season, rnd, driver_id, round(float(t - best), 3)),
        )
        n += 1
    conn.commit()
    return n


def ingest_seasons(conn: sqlite3.Connection, seasons: list[int]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))
    codes = _code_map(conn)
    for season in seasons:
        rounds = [r["round"] for r in conn.execute(
            "SELECT DISTINCT round FROM results WHERE season=? ORDER BY round", (season,))]
        for rnd in rounds:
            try:
                n = ingest_round(conn, season, rnd, codes)
                print(f"  {season} R{rnd}: {n} drivers", flush=True)
            except Exception as e:  # missing/partial session data
                print(f"  {season} R{rnd}: skipped ({type(e).__name__})", flush=True)


def main(argv: list[str]) -> int:
    seasons = [int(a) for a in argv] or [2025, 2026]
    conn = connect()
    try:
        ingest_seasons(conn, seasons)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
