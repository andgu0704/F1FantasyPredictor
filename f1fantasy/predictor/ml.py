"""ML predictor.

Trains a ridge model on causal Jolpica features to predict each driver's
next-race "goodness", then expresses that as a learned factor on the driver's
real season-average fantasy points — the same baseline-and-factor combination as
the heuristic, but with the multiplier learned from data instead of hand-tuned.

    expected = f_avg + (factor - 1) * max(f_avg, SCALE_FLOOR)
    factor   = clamp(predicted_goodness / season_form_baseline)

Constructors have no per-car model here, so they fall back to f_avg (the
optimizer still prices them correctly); driver selection is where the model adds
value. The ML model is fit on every ingestion-time call — the dataset is tiny.
"""

from __future__ import annotations

import sqlite3

import numpy as np

from f1fantasy.features import build_rows, upcoming_features
from f1fantasy.ml_model import RidgeModel
from f1fantasy.predictor.base import Pick, PredictorBase

SCALE_FLOOR = 5.0
FACTOR_CLAMP = (0.6, 1.4)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class MLPredictor(PredictorBase):
    name = "ml-ridge-goodness-factor"

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha

    def _train(self, conn: sqlite3.Connection) -> RidgeModel:
        rows = build_rows(conn)
        if len(rows) < 20:
            raise RuntimeError("Not enough history to train the ML predictor.")
        X = np.array([r.features for r in rows])
        y = np.array([r.label for r in rows])
        return RidgeModel(self.alpha).fit(X, y)

    def predict(self, conn: sqlite3.Connection, season: int, gameday: int) -> list[Pick]:
        model = self._train(conn)
        upcoming = upcoming_features(conn, season)

        # Predicted goodness + baseline per Jolpica driver.
        factors: dict[str, float] = {}
        for driver_id, (feats, baseline) in upcoming.items():
            pred = float(model.predict(np.array(feats))[0])
            factors[driver_id] = _clamp(pred / baseline, *FACTOR_CLAMP) if baseline > 0 else 1.0

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

            factor = factors.get(r["jolpica_id"], 1.0) if r["entity_type"] == "driver" else 1.0
            expected = baseline + (factor - 1.0) * max(baseline, SCALE_FLOOR)
            picks.append(Pick(r["entity_type"], r["fantasy_id"],
                              r["name"] or r["team_name"], float(r["price"]), expected))
        return picks
