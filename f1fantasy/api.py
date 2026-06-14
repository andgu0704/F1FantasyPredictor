"""FastAPI backend exposing the recommender to the web frontend.

    uv run uvicorn f1fantasy.api:app --reload

Endpoints:
    GET /api/health
    GET /api/gameday                      -> current season/gameday/budget
    GET /api/picks?predictor=heuristic    -> every pick with price + expected pts
    GET /api/recommend?predictor=heuristic&drs_boost=true -> optimal lineup
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from f1fantasy.db import connect
from f1fantasy.optimizer import optimize_lineup
from f1fantasy.predictor.base import PredictorBase, Pick
from f1fantasy.predictor.heuristic import HeuristicPredictor
from f1fantasy.predictor.ml import MLPredictor
from f1fantasy.predictor.naive import NaivePredictor
from f1fantasy.recommend import current_gameday

app = FastAPI(title="F1 Fantasy Predictor")

# The Vite dev server runs on a different port; allow it during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_PREDICTORS: dict[str, type[PredictorBase]] = {
    "heuristic": HeuristicPredictor,
    "naive": NaivePredictor,
    "ml": MLPredictor,
}


@contextmanager
def _db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def _get_predictor(name: str) -> PredictorBase:
    try:
        return _PREDICTORS[name]()
    except KeyError:
        raise HTTPException(404, f"Unknown predictor '{name}'. Options: {list(_PREDICTORS)}")


def _pick_json(p: Pick) -> dict:
    return {
        "entity_type": p.entity_type,
        "fantasy_id": p.fantasy_id,
        "name": p.name,
        "price": round(p.price, 1),
        "expected_points": round(p.expected_points, 1),
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/gameday")
def gameday() -> dict:
    with _db() as conn:
        season, gd, budget = current_gameday(conn)
    return {"season": season, "gameday": gd, "budget": budget}


@app.get("/api/predictors")
def predictors() -> dict:
    return {"predictors": [{"id": k, "name": v.name} for k, v in _PREDICTORS.items()]}


@app.get("/api/picks")
def picks(predictor: str = "heuristic") -> dict:
    pred = _get_predictor(predictor)
    with _db() as conn:
        season, gd, _ = current_gameday(conn)
        items = pred.predict(conn, season, gd)
    items.sort(key=lambda p: (p.entity_type, -p.expected_points))
    return {"predictor": pred.name, "picks": [_pick_json(p) for p in items]}


@app.get("/api/recommend")
def recommend(
    predictor: str = "heuristic",
    drs_boost: bool = True,
    budget: float | None = Query(None, gt=0, description="Override the budget cap."),
) -> dict:
    pred = _get_predictor(predictor)
    with _db() as conn:
        season, gd, live_budget = current_gameday(conn)
        items = pred.predict(conn, season, gd)
        lineup = optimize_lineup(items, budget=budget or live_budget, drs_boost=drs_boost)
    return {
        "season": season,
        "gameday": gd,
        "budget": budget or live_budget,
        "predictor": pred.name,
        "total_price": round(lineup.total_price, 1),
        "expected_points": round(lineup.expected_points, 1),
        "boosted_id": lineup.boosted.fantasy_id if lineup.boosted else None,
        "drivers": [_pick_json(p) for p in lineup.drivers],
        "constructors": [_pick_json(p) for p in lineup.constructors],
    }
