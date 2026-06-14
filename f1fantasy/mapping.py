"""Bridge the F1 Fantasy entity ids to Jolpica ids.

The fantasy feeds identify drivers/teams by the game's own ids and display
names ("Kimi Antonelli", "Racing Bulls"); Jolpica uses stable slugs
("antonelli", "rb"). This module matches the two and fills fantasy_entity_map
so price/points can be joined to historical results.

Matching is deliberately conservative: drivers match on an accent-normalized
family name (unambiguous for the current grid), constructors match on a
normalized name with a small set of explicit overrides for cases that no
string-similarity heuristic gets right (e.g. "Racing Bulls" -> "rb"). Anything
that does not match is returned for a human to resolve rather than guessed.
"""

from __future__ import annotations

import sqlite3
import unicodedata

# Fantasy constructor display name -> Jolpica constructor_id, for cases the
# normalized matcher cannot resolve on its own.
_CONSTRUCTOR_OVERRIDES = {
    "Racing Bulls": "rb",
    "Red Bull Racing": "red_bull",
}


def _norm(s: str) -> str:
    """Lowercase, strip accents and non-alphanumerics."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return "".join(ch for ch in s.lower() if ch.isalnum() or ch == " ").strip()


def _map_drivers(conn: sqlite3.Connection) -> tuple[list[tuple[str, str]], list[dict]]:
    by_family = {}
    for row in conn.execute("SELECT driver_id, family_name FROM drivers"):
        by_family[_norm(row["family_name"]).split()[-1]] = row["driver_id"]

    pairs, unmatched = [], []
    for row in conn.execute(
        "SELECT fantasy_id, name FROM fantasy_stats WHERE entity_type='driver'"
    ):
        family = _norm(row["name"]).split()[-1]
        jolpica = by_family.get(family)
        if jolpica:
            pairs.append((row["fantasy_id"], jolpica))
        else:
            unmatched.append({"type": "driver", "fantasy_id": row["fantasy_id"], "name": row["name"]})
    return pairs, unmatched


def _map_constructors(conn: sqlite3.Connection) -> tuple[list[tuple[str, str]], list[dict]]:
    # Prefer teams active in the latest season so e.g. "Audi" resolves to the
    # current `audi` entry and not the prior-year `sauber`.
    candidates = list(conn.execute(
        """SELECT constructor_id, name FROM constructors
           WHERE constructor_id IN (
               SELECT DISTINCT constructor_id FROM results
               WHERE season = (SELECT MAX(season) FROM results))"""
    )) or list(conn.execute("SELECT constructor_id, name FROM constructors"))
    by_norm = {_norm(r["name"]): r["constructor_id"] for r in candidates}

    pairs, unmatched = [], []
    for row in conn.execute(
        "SELECT fantasy_id, name FROM fantasy_stats WHERE entity_type='constructor'"
    ):
        name = row["name"]
        jolpica = _CONSTRUCTOR_OVERRIDES.get(name)
        if not jolpica:
            fn = _norm(name)
            # Exact, then containment either direction (e.g. "alpine" in
            # "alpine f1 team", "haas" in "haas f1 team").
            jolpica = by_norm.get(fn) or next(
                (cid for jn, cid in by_norm.items() if fn in jn or jn in fn), None
            )
        if jolpica:
            pairs.append((row["fantasy_id"], jolpica))
        else:
            unmatched.append({"type": "constructor", "fantasy_id": row["fantasy_id"], "name": name})
    return pairs, unmatched


def build_entity_map(conn: sqlite3.Connection) -> list[dict]:
    """Populate fantasy_entity_map; return the list of unmatched entities."""
    dpairs, dun = _map_drivers(conn)
    cpairs, cun = _map_constructors(conn)
    conn.executemany(
        """INSERT INTO fantasy_entity_map (entity_type, fantasy_id, jolpica_id)
           VALUES (?, ?, ?)
           ON CONFLICT(entity_type, fantasy_id) DO UPDATE SET jolpica_id=excluded.jolpica_id""",
        [("driver", f, j) for f, j in dpairs] + [("constructor", f, j) for f, j in cpairs],
    )
    conn.commit()
    return dun + cun


if __name__ == "__main__":
    from f1fantasy.db import connect

    conn = connect()
    unmatched = build_entity_map(conn)
    n = conn.execute("SELECT COUNT(*) c FROM fantasy_entity_map").fetchone()["c"]
    print(f"Mapped {n} entities; {len(unmatched)} unmatched.")
    for u in unmatched:
        print("  UNMATCHED:", u)
