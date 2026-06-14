"""Client + ingestion for the Official F1 Fantasy data feeds.

The modern game (run on SportzInteractive's platform) exposes a set of public,
unauthenticated JSON feeds under https://fantasy.formula1.com/feeds/ :

  apps/web_config.json              -> current tourId + statistics endpoints
  limits/constraints.json           -> budget cap, current gameday, deadline
  statistics/drivers_{tour}.json    -> per-driver price + season fantasy stats
  statistics/constructors_{tour}.json

Each statistics feed is a list of stat *categories*; every category repeats the
full roster under `participants`. For a given entity, `curvalue` is constant
across categories (it is the current price), while `statvalue` is the value of
that one category (fPoints, fAvg, ...). We pivot these into one row per entity.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import httpx

FEEDS_BASE = "https://fantasy.formula1.com/feeds"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# statvalue keys we lift into dedicated columns (others are ignored).
_STAT_COLUMNS = {
    "fPoints": "f_points",
    "fAvg": "f_avg",
    "pointsPermillion": "points_per_million",
    "priceChange": "price_change",
}


class FantasyClient:
    def __init__(self, base_url: str = FEEDS_BASE, timeout: float = 30.0) -> None:
        self._client = httpx.Client(base_url=base_url, headers=_HEADERS, timeout=timeout)

    def __enter__(self) -> "FantasyClient":
        return self

    def __exit__(self, *exc) -> None:
        self._client.close()

    def _json(self, path: str) -> dict:
        resp = self._client.get(f"/{path.lstrip('/')}")
        resp.raise_for_status()
        return resp.json()

    def tour_id(self) -> int:
        return int(self._json("apps/web_config.json")["tourId"])

    def constraints(self) -> dict:
        """Live game parameters (budget cap, gameday, deadline)."""
        return self._json("limits/constraints.json")["Data"]["Value"]

    def statistics(self, entity_type: str, tour_id: int) -> tuple[int, list[dict]]:
        """Return (season, [one pivoted record per entity]) for the given type."""
        feed = "drivers" if entity_type == "driver" else "constructors"
        data = self._json(f"statistics/{feed}_{tour_id}.json")["Data"]
        season = int(data["season"])
        return season, _pivot_statistics(data["statistics"], entity_type)


def _pivot_statistics(categories: list[dict], entity_type: str) -> list[dict]:
    """Collapse the category-major feed into one dict per entity."""
    by_id: dict[str, dict] = {}
    for cat in categories:
        key = cat["config"]["key"]
        for p in cat["participants"]:
            pid = p.get("playerid")
            if not pid:
                # Some categories omit the id for an entity with no value yet
                # (e.g. a brand-new team with zero top-finishes); it is still
                # captured via the categories where its id is present.
                continue
            rec = by_id.setdefault(
                pid,
                {
                    "fantasy_id": pid,
                    "name": p.get("playername"),       # absent for constructors
                    "team_name": p.get("teamname"),
                    "price": p.get("curvalue"),
                },
            )
            if key in _STAT_COLUMNS:
                rec[_STAT_COLUMNS[key]] = p.get("statvalue")
    # Constructors use teamname as their name.
    if entity_type == "constructor":
        for rec in by_id.values():
            rec["name"] = rec.get("name") or rec.get("team_name")
    return list(by_id.values())


def ingest_fantasy(conn: sqlite3.Connection, client: FantasyClient) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    c = client.constraints()
    gameday = int(c["GamedayId"])
    tour = client.tour_id()

    counts = {"drivers": 0, "constructors": 0}
    season = None
    for entity_type in ("driver", "constructor"):
        season, records = client.statistics(entity_type, tour)
        for rec in records:
            conn.execute(
                """INSERT INTO fantasy_stats
                     (season, gameday, entity_type, fantasy_id, name, team_name,
                      price, f_points, f_avg, points_per_million, price_change, captured_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(season, gameday, entity_type, fantasy_id) DO UPDATE SET
                     name=excluded.name, team_name=excluded.team_name, price=excluded.price,
                     f_points=excluded.f_points, f_avg=excluded.f_avg,
                     points_per_million=excluded.points_per_million,
                     price_change=excluded.price_change, captured_at=excluded.captured_at""",
                (
                    season, gameday, entity_type, rec["fantasy_id"], rec.get("name"),
                    rec.get("team_name"), rec.get("price"), rec.get("f_points"),
                    rec.get("f_avg"), rec.get("points_per_million"),
                    rec.get("price_change"), now,
                ),
            )
            counts[entity_type + "s"] += 1

    conn.execute(
        """INSERT INTO game_state (season, gameday, max_team_value, deadline, captured_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(season, gameday) DO UPDATE SET
             max_team_value=excluded.max_team_value, deadline=excluded.deadline,
             captured_at=excluded.captured_at""",
        (season, gameday, float(c["MaxTeamValue"]), c.get("DeadlineDate"), now),
    )
    conn.commit()
    counts["gameday"] = gameday
    counts["budget"] = float(c["MaxTeamValue"])
    return counts
