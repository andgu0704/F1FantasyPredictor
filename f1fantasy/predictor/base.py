"""Predictor interface.

A predictor turns the current state of the world into an expected fantasy-points
number for every pickable entity at the upcoming Grand Prix. The optimizer only
ever sees this output plus prices, so any predictor (naive average, heuristic,
ML) is interchangeable as long as it returns this shape.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Pick:
    """A pickable entity with everything the optimizer needs."""

    entity_type: str          # 'driver' | 'constructor'
    fantasy_id: str
    name: str
    price: float
    expected_points: float


class PredictorBase:
    """Subclass and implement `predict`."""

    name = "base"

    def predict(self, conn: sqlite3.Connection, season: int, gameday: int) -> list[Pick]:
        raise NotImplementedError
