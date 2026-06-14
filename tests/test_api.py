"""API smoke tests via FastAPI TestClient (uses the live DB)."""

from __future__ import annotations

import warnings

import pytest
from fastapi.testclient import TestClient

from f1fantasy.api import app
from f1fantasy.db import connect

warnings.filterwarnings("ignore")
client = TestClient(app)


def _has_data() -> bool:
    return connect().execute("SELECT COUNT(*) c FROM fantasy_stats").fetchone()["c"] > 0


pytestmark = pytest.mark.skipif(not _has_data(), reason="database not populated")


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_gameday_shape():
    j = client.get("/api/gameday").json()
    assert {"season", "gameday", "budget"} <= j.keys()


@pytest.mark.parametrize("predictor", ["naive", "heuristic", "ml"])
def test_recommend_valid_lineup(predictor):
    j = client.get(f"/api/recommend?predictor={predictor}").json()
    assert len(j["drivers"]) == 5
    assert len(j["constructors"]) == 2
    assert j["total_price"] <= j["budget"] + 1e-6


def test_budget_override_constrains_spend():
    j = client.get("/api/recommend?budget=60").json()
    assert j["total_price"] <= 60.0 + 1e-6


def test_unknown_predictor_404():
    assert client.get("/api/recommend?predictor=nope").status_code == 404


def test_chips_value_keys():
    j = client.get("/api/chips").json()
    assert "valued" in j and "info_only" in j
    assert {c["chip"] for c in j["valued"]} == {"wildcard", "limitless", "extra_drs", "no_negative"}
