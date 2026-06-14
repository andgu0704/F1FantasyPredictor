"""Ingest a season of Jolpica data into the local SQLite database.

Usage:
    uv run python -m f1fantasy.ingestion.ingest 2025 2026

Idempotent: every write is an upsert keyed on natural keys, so re-running
after a race weekend simply refreshes the affected rows.
"""

from __future__ import annotations

import sqlite3
import sys

from f1fantasy.db import connect
from f1fantasy.ingestion.fantasy import FantasyClient, ingest_fantasy
from f1fantasy.ingestion.jolpica import JolpicaClient
from f1fantasy.mapping import build_entity_map


def _lap_time_to_ms(value: str | None) -> int | None:
    """Parse a lap time like '1:15.912' or '15.912' into milliseconds."""
    if not value:
        return None
    minutes = 0
    if ":" in value:
        mins, _, rest = value.partition(":")
        minutes = int(mins)
        value = rest
    seconds = float(value)
    return int(round((minutes * 60 + seconds) * 1000))


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _upsert_driver(conn: sqlite3.Connection, d: dict) -> None:
    conn.execute(
        """INSERT INTO drivers (driver_id, code, permanent_no, given_name, family_name, nationality)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(driver_id) DO UPDATE SET
             code=excluded.code, permanent_no=excluded.permanent_no,
             given_name=excluded.given_name, family_name=excluded.family_name,
             nationality=excluded.nationality""",
        (
            d["driverId"], d.get("code"), _int_or_none(d.get("permanentNumber")),
            d.get("givenName"), d.get("familyName"), d.get("nationality"),
        ),
    )


def _upsert_constructor(conn: sqlite3.Connection, c: dict) -> None:
    conn.execute(
        """INSERT INTO constructors (constructor_id, name, nationality)
           VALUES (?, ?, ?)
           ON CONFLICT(constructor_id) DO UPDATE SET
             name=excluded.name, nationality=excluded.nationality""",
        (c["constructorId"], c.get("name"), c.get("nationality")),
    )


def _upsert_race(conn: sqlite3.Connection, season: int, race: dict) -> None:
    circuit = race.get("Circuit", {})
    is_sprint = 1 if race.get("Sprint") else 0
    conn.execute(
        """INSERT INTO races (season, round, race_name, circuit_id, circuit_name, date, is_sprint)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(season, round) DO UPDATE SET
             race_name=excluded.race_name, circuit_id=excluded.circuit_id,
             circuit_name=excluded.circuit_name, date=excluded.date,
             is_sprint=MAX(races.is_sprint, excluded.is_sprint)""",
        (
            season, int(race["round"]), race.get("raceName"),
            circuit.get("circuitId"), circuit.get("circuitName"), race.get("date"), is_sprint,
        ),
    )


def ingest_season(conn: sqlite3.Connection, client: JolpicaClient, season: int) -> dict:
    counts = {"races": 0, "results": 0, "qualifying": 0}

    # Schedule first, so result rows have a parent race to reference.
    for race in client.races(season):
        _upsert_race(conn, season, race)
        counts["races"] += 1

    # Race results.
    for race in client.results(season):
        rnd = int(race["round"])
        _upsert_race(conn, season, race)
        for res in race.get("Results", []):
            driver, constructor = res["Driver"], res["Constructor"]
            _upsert_driver(conn, driver)
            _upsert_constructor(conn, constructor)
            fl = res.get("FastestLap", {})
            conn.execute(
                """INSERT INTO results
                     (season, round, driver_id, constructor_id, grid, position,
                      position_text, points, laps, status, fastest_lap_rank)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(season, round, driver_id) DO UPDATE SET
                     constructor_id=excluded.constructor_id, grid=excluded.grid,
                     position=excluded.position, position_text=excluded.position_text,
                     points=excluded.points, laps=excluded.laps, status=excluded.status,
                     fastest_lap_rank=excluded.fastest_lap_rank""",
                (
                    season, rnd, driver["driverId"], constructor["constructorId"],
                    _int_or_none(res.get("grid")), _int_or_none(res.get("position")),
                    res.get("positionText"), float(res.get("points", 0)),
                    _int_or_none(res.get("laps")), res.get("status"),
                    _int_or_none(fl.get("rank")),
                ),
            )
            counts["results"] += 1

    # Qualifying.
    for race in client.qualifying(season):
        rnd = int(race["round"])
        for q in race.get("QualifyingResults", []):
            driver, constructor = q["Driver"], q["Constructor"]
            _upsert_driver(conn, driver)
            _upsert_constructor(conn, constructor)
            conn.execute(
                """INSERT INTO qualifying
                     (season, round, driver_id, constructor_id, position, q1_ms, q2_ms, q3_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(season, round, driver_id) DO UPDATE SET
                     constructor_id=excluded.constructor_id, position=excluded.position,
                     q1_ms=excluded.q1_ms, q2_ms=excluded.q2_ms, q3_ms=excluded.q3_ms""",
                (
                    season, rnd, driver["driverId"], constructor["constructorId"],
                    _int_or_none(q.get("position")),
                    _lap_time_to_ms(q.get("Q1")), _lap_time_to_ms(q.get("Q2")),
                    _lap_time_to_ms(q.get("Q3")),
                ),
            )
            counts["qualifying"] += 1

    # Sprint results (sprint weekends only).
    counts["sprint"] = 0
    for race in client.sprint(season):
        rnd = int(race["round"])
        conn.execute("UPDATE races SET is_sprint=1 WHERE season=? AND round=?", (season, rnd))
        for res in race.get("SprintResults", []):
            driver, constructor = res["Driver"], res["Constructor"]
            _upsert_driver(conn, driver)
            _upsert_constructor(conn, constructor)
            conn.execute(
                """INSERT INTO sprint_results
                     (season, round, driver_id, constructor_id, grid, position,
                      position_text, points, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(season, round, driver_id) DO UPDATE SET
                     constructor_id=excluded.constructor_id, grid=excluded.grid,
                     position=excluded.position, position_text=excluded.position_text,
                     points=excluded.points, status=excluded.status""",
                (
                    season, rnd, driver["driverId"], constructor["constructorId"],
                    _int_or_none(res.get("grid")), _int_or_none(res.get("position")),
                    res.get("positionText"), float(res.get("points", 0)), res.get("status"),
                ),
            )
            counts["sprint"] += 1

    conn.commit()
    return counts


def main(argv: list[str]) -> int:
    seasons = [int(a) for a in argv] or [2025, 2026]
    conn = connect()
    try:
        with JolpicaClient() as client:
            for season in seasons:
                print(f"Ingesting Jolpica {season} ...", flush=True)
                counts = ingest_season(conn, client, season)
                print(f"  {season}: {counts}", flush=True)
        print("Ingesting F1 Fantasy market ...", flush=True)
        with FantasyClient() as fclient:
            fcounts = ingest_fantasy(conn, fclient)
            print(f"  fantasy: {fcounts}", flush=True)
        print("Building fantasy↔Jolpica entity map ...", flush=True)
        unmatched = build_entity_map(conn)
        print(f"  unmatched: {len(unmatched)}", flush=True)
        for u in unmatched:
            print(f"    ! {u}", flush=True)
        # FastF1 race-pace (only the newest round downloads; rest is cached).
        try:
            from f1fantasy.ingestion.fastf1_pace import ingest_seasons
            print("Ingesting FastF1 race pace ...", flush=True)
            ingest_seasons(conn, seasons)
        except Exception as e:
            print(f"  race pace skipped: {type(e).__name__}: {e}", flush=True)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
