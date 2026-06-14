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
  It is **transfer-aware**: given your current team it maximizes net points
  (gross − 10 × extra transfers beyond your free allowance) and values the
  **chips** (Wildcard, Limitless, Extra DRS) by re-solving under each chip's rules.

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 1 | Data pipeline: Jolpica ingestion → SQLite | ✅ done |
| 1b | Fantasy prices/points ingestion | ✅ done |
| 2 | Entity mapping + ILP optimizer (naive predictor) | ✅ done |
| 3 | Heuristic expected-points predictor | ✅ done |
| 4 | FastAPI backend + React/Vite frontend | ✅ done |
| 5 | ML predictor + backtest harness | ✅ done |
| 6 | Transfer-aware optimizer + chips + per-race refresh | ✅ done |
| 7 | FastF1 pace features + budget input + single-app deploy | ✅ done |

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
  features.py           causal feature engineering (results + quali + race pace)
  ingestion/fastf1_pace.py  median race-pace gap per driver (FastF1)
  ml_model.py           ridge regression (numpy, closed-form)
  backtest.py           walk-forward evaluation of the predictors
  optimizer.py          transfer-aware ILP (budget + roster + DRS + penalty)
  chips.py              chip (Wildcard/Limitless/Extra DRS) valuation
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

Open http://localhost:5173:
- Leave the team empty for a **fresh-build** optimal lineup, or enter **your
  current team** (5 drivers + 2 constructors) to get **transfer suggestions**
  (OUT/IN) that respect the −10 penalty and your free-transfer count.
- The **chip panel** shows how many extra points Wildcard / Limitless / Extra
  DRS would buy this race, highlighting the best one.
- **↻ Refresh data** re-ingests the latest Jolpica + fantasy feeds, so the app
  tracks each upcoming Grand Prix. For hands-off updates, schedule the ingest
  weekly (e.g. cron): `uv run python -m f1fantasy.ingestion.ingest`.

## Deploy (single app)

In production FastAPI serves the built frontend, so it's one process:

```bash
cd frontend && npm run build && cd ..      # build the UI into frontend/dist
uv run uvicorn f1fantasy.api:app --port 8000   # serves UI + API at :8000
```

Or with Docker (builds the UI, ingests on first boot, then serves):

```bash
docker build -t f1fantasy . && docker run -p 8000:8000 f1fantasy
```

## Predictor accuracy (backtest)

```bash
uv run python -m f1fantasy.backtest
```

Walk-forward over the available rounds, scoring each predictor's driver ranking
against actual race results (Spearman ρ, top-5 hit rate):

| predictor | Spearman ρ | top-5 hit |
|-----------|-----------:|----------:|
| naive (season avg) | 0.49 | **71%** |
| heuristic          | 0.48 | 67% |
| ml (pace-aware)    | **0.51** | 69% |

Adding **pace features** — qualifying gap-to-pole (from Jolpica) and median
race-pace gap (from **FastF1**) — lifts the ML model from 0.48 to 0.51 Spearman,
past the season-average baseline, confirming pace is a cleaner signal than
finishing position. Naive still edges the **top-5 hit rate** (the more practical
metric), so it remains the default; ML is the better overall-ranking model and
the slot where richer features keep paying off. All predictors are
interchangeable behind `PredictorBase`.
