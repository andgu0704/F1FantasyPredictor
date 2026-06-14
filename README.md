# F1 Fantasy Predictor

Builds the optimal Official F1 Fantasy lineup (5 drivers + 2 constructors) within
the budget cap for each Grand Prix.

The system is two decoupled halves:

- **Predictor** — estimates expected fantasy points per driver/constructor for the
  upcoming GP. Phased: a debuggable heuristic first, an ML model later, both behind
  one interface.
- **Optimizer** — an integer linear program that picks the roster maximizing
  Σ expected-points subject to budget + roster constraints. Consumes only a
  `{entity: (expected_points, price)}` table, so the model can be swapped freely.

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 1 | Data pipeline: Jolpica ingestion → SQLite | ✅ done |
| 1b | Fantasy prices/points ingestion | ✅ done |
| 2 | Entity mapping + ILP optimizer (naive predictor) | ✅ done |
| 3 | Heuristic expected-points predictor | ✅ done |
| 4 | FastAPI backend + React/Vite frontend | ✅ done |
| 5 | ML predictor + backtest harness | ✅ done |

## Data sources

- **[Jolpica-F1](https://github.com/jolpica/jolpica-f1)** — Ergast successor;
  historical + current results, qualifying, schedule (1950–present). Updated the
  Monday after each race weekend.
- **Official F1 Fantasy feeds** — driver/constructor prices and fantasy points.
  The modern game (SportzInteractive platform) serves public, unauthenticated
  JSON under `https://fantasy.formula1.com/feeds/`:
  - `apps/web_config.json` — current `tourId` + statistics endpoint paths
  - `limits/constraints.json` — budget cap ($100M), current gameday, deadline
  - `statistics/drivers_{tour}.json`, `statistics/constructors_{tour}.json` —
    per-entity current price (`curvalue`) + season fantasy points/averages.
    Note: the older `fantasy-api.formula1.com/f1/2022` host every old library
    uses is dead; these feeds are the current source.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                      # install deps
uv run python -m f1fantasy.ingestion.ingest  # ingest 2025 + 2026 into data/f1fantasy.db
```

## Layout

```
f1fantasy/
  db.py                 SQLite schema + connection
  ingestion/
    jolpica.py          Jolpica API client (paginated, rate-limited)
    fantasy.py          F1 Fantasy feeds client + market ingestion
    ingest.py           Jolpica + Fantasy → SQLite upsert pipeline
  mapping.py            fantasy_id ↔ Jolpica id bridge (fills fantasy_entity_map)
  predictor/
    base.py             PredictorBase + Pick contract
    naive.py            season-average baseline predictor
    heuristic.py        form + track + reliability predictor (default)
    ml.py               ridge model as a learned baseline factor
  features.py           causal feature engineering from Jolpica results
  ml_model.py           ridge regression (numpy, closed-form)
  backtest.py           walk-forward evaluation of the predictors
  optimizer.py          ILP roster optimizer (budget + roster + DRS boost)
  recommend.py          predictor + optimizer + live game_state → Lineup
  api.py                FastAPI app (/api/recommend, /api/picks, ...)
frontend/               React/Vite UI (proxies /api to the backend)
data/f1fantasy.db       local database (gitignored)
```

## Recommend a lineup

```bash
uv run python -m f1fantasy.recommend    # prints the optimal lineup for the gameday
```

## Web app

Two processes — the FastAPI backend and the Vite dev server (which proxies
`/api` to the backend):

```bash
uv run uvicorn f1fantasy.api:app --port 8000     # terminal 1: API
cd frontend && npm install && npm run dev        # terminal 2: UI at :5173
```

Open http://localhost:5173 — pick the predictor and toggle the DRS boost; the
lineup re-optimizes live.

## Predictor accuracy (backtest)

```bash
uv run python -m f1fantasy.backtest
```

Walk-forward over the available rounds, scoring each predictor's driver ranking
against actual race results (Spearman ρ, top-5 hit rate):

| predictor | Spearman ρ | top-5 hit |
|-----------|-----------:|----------:|
| naive (season avg) | 0.49 | 71% |
| heuristic          | 0.48 | 67% |
| ml (ridge)         | 0.48 | 68% |

Honest finding: season-to-date form is a strong baseline, and the form/track/
reliability signals (hand-tuned or learned) don't beat it on position-derived
features. Beating it needs genuinely new inputs — qualifying/practice pace,
weather, upgrades (FastF1) — or per-race fantasy-points labels. The predictors
are interchangeable behind `PredictorBase`, so adding richer features is local
to the predictor layer.
