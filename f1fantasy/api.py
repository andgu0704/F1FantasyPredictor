"""FastAPI backend exposing the recommender to the web frontend.

    uv run uvicorn f1fantasy.api:app --reload

Endpoints:
    GET  /api/health
    GET  /api/gameday                  -> season/gameday/budget/deadline
    GET  /api/predictors
    GET  /api/picks?predictor=naive    -> every pick with price + expected pts
    GET  /api/recommend                -> optimal lineup (optionally transfer-aware)
    GET  /api/chips                     -> base lineup + chip valuations
    POST /api/refresh                  -> re-run ingestion for the latest gameday
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from f1fantasy.chips import evaluate_chips
from f1fantasy.db import connect
from f1fantasy.optimizer import Lineup, optimize_lineup
from f1fantasy.predictor.base import PredictorBase, Pick
from f1fantasy.predictor.heuristic import HeuristicPredictor
from f1fantasy.predictor.ml import MLPredictor
from f1fantasy.predictor.naive import NaivePredictor
from f1fantasy.recommend import current_gameday

app = FastAPI(title="F1 Fantasy Predictor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_PREDICTORS: dict[str, type[PredictorBase]] = {
    "heuristic": HeuristicPredictor,
    "naive": NaivePredictor,
    "ml": MLPredictor,
}

# Chips the optimizer values vs. surfaces-only (in-race / variance / mobile).
_INFO_CHIPS = ["final_fix", "no_negative", "auto_pilot"]


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


def _parse_team(current_team: str | None) -> set[str] | None:
    if not current_team:
        return None
    ids = {t.strip() for t in current_team.split(",") if t.strip()}
    return ids or None


def _pick_json(p: Pick) -> dict:
    return {
        "entity_type": p.entity_type,
        "fantasy_id": p.fantasy_id,
        "name": p.name,
        "price": round(p.price, 1),
        "expected_points": round(p.expected_points, 1),
    }


def _lineup_json(lineup: Lineup, season: int, gd: int, budget: float, predictor: str) -> dict:
    return {
        "season": season,
        "gameday": gd,
        "budget": budget,
        "predictor": predictor,
        "total_price": round(lineup.total_price, 1),
        "gross_points": round(lineup.gross_points, 1),
        "net_points": round(lineup.net_points, 1),
        "penalty": round(lineup.penalty, 1),
        "num_transfers": lineup.num_transfers,
        "drs_multiplier": lineup.drs_multiplier,
        "boosted_id": lineup.boosted.fantasy_id if lineup.boosted else None,
        "transfers_in": [_pick_json(p) for p in lineup.transfers_in],
        "transfers_out": [_pick_json(p) for p in lineup.transfers_out],
        "drivers": [_pick_json(p) for p in lineup.drivers],
        "constructors": [_pick_json(p) for p in lineup.constructors],
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/gameday")
def gameday() -> dict:
    with _db() as conn:
        season, gd, budget = current_gameday(conn)
        row = conn.execute(
            "SELECT deadline FROM game_state WHERE season=? AND gameday=?", (season, gd)
        ).fetchone()
    return {"season": season, "gameday": gd, "budget": budget,
            "deadline": row["deadline"] if row else None}


@app.get("/api/predictors")
def predictors() -> dict:
    return {"predictors": [{"id": k, "name": v.name} for k, v in _PREDICTORS.items()]}


@app.get("/api/picks")
def picks(predictor: str = "naive") -> dict:
    pred = _get_predictor(predictor)
    with _db() as conn:
        season, gd, _ = current_gameday(conn)
        items = pred.predict(conn, season, gd)
    items.sort(key=lambda p: (p.entity_type, -p.expected_points))
    return {"predictor": pred.name, "picks": [_pick_json(p) for p in items]}


# DRS multiplier per chip choice; "extra_drs" triples the boost.
_CHIP_KWARGS = {
    "none": {},
    "wildcard": {"unlimited_transfers": True},
    "limitless": {"unlimited_transfers": True, "unlimited_budget": True},
    "extra_drs": {"drs_multiplier": 3},
}


@app.get("/api/recommend")
def recommend(
    predictor: str = "naive",
    drs_boost: bool = True,
    budget: float | None = Query(None, gt=0, description="Override the budget cap."),
    current_team: str | None = Query(None, description="Comma-separated fantasy_ids."),
    free_transfers: int = Query(2, ge=0),
    chip: str = Query("none"),
) -> dict:
    if chip not in _CHIP_KWARGS:
        raise HTTPException(404, f"Unknown chip '{chip}'. Options: {list(_CHIP_KWARGS)}")
    pred = _get_predictor(predictor)
    with _db() as conn:
        season, gd, live_budget = current_gameday(conn)
        items = pred.predict(conn, season, gd)
        lineup = optimize_lineup(
            items, budget=budget or live_budget, drs_boost=drs_boost,
            current_team=_parse_team(current_team), free_transfers=free_transfers,
            **_CHIP_KWARGS[chip],
        )
    out = _lineup_json(lineup, season, gd, budget or live_budget, pred.name)
    out["chip"] = chip
    return out


@app.get("/api/chips")
def chips(
    predictor: str = "naive",
    budget: float | None = Query(None, gt=0),
    current_team: str | None = Query(None),
    free_transfers: int = Query(2, ge=0),
) -> dict:
    pred = _get_predictor(predictor)
    with _db() as conn:
        season, gd, live_budget = current_gameday(conn)
        items = pred.predict(conn, season, gd)
        base, chip_values = evaluate_chips(
            items, budget or live_budget, current_team=_parse_team(current_team),
            free_transfers=free_transfers,
        )
    return {
        "base_net_points": round(base.net_points, 1),
        "valued": [
            {"chip": c.chip, "delta": round(c.delta, 1),
             "lineup": _lineup_json(c.lineup, season, gd, budget or live_budget, pred.name)}
            for c in chip_values
        ],
        "info_only": _INFO_CHIPS,
    }


@app.post("/api/refresh")
def refresh() -> dict:
    """Re-ingest the latest Jolpica + fantasy data so the app tracks each race."""
    from f1fantasy.ingestion.ingest import main as ingest_main

    rc = ingest_main([])  # default seasons
    with _db() as conn:
        season, gd, budget = current_gameday(conn)
    return {"ok": rc == 0, "season": season, "gameday": gd, "budget": budget}


# Serve the built frontend (single-app deploy). Mounted last so /api/* wins.
# In dev the Vite server serves the UI instead and this dir simply won't exist.
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
