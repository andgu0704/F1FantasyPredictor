# Deployment

This app (FastAPI + the PuLP/CBC solver binary + a SQLite file + a React
monorepo) runs best in a **container**, not on serverless. Render and Railway
both build the `Dockerfile` directly, so they run the exact app that works
locally. Vercel was tried and dropped — its serverless model fights the native
solver binary and read-only filesystem.

## Render (recommended — runs the real container)

Render builds the `Dockerfile`, so it runs the exact app that works locally —
no serverless constraints (PuLP's solver, read-only FS).

### Steps

1. Push the repo to GitHub.
2. On [render.com](https://render.com): **New → Blueprint** → select this repo.
   Render reads `render.yaml` and provisions the service automatically.
3. Done. It serves at `https://f1-fantasy.onrender.com` (or your chosen name).

### Notes

- The database is **baked into the image** (committed `data/f1fantasy.db`), so
  boot is instant — no ingestion on startup.
- To update data: ingest locally, commit the new `data/f1fantasy.db`, and push —
  Render auto-redeploys (`autoDeploy: true`).
- Free tier spins down after inactivity; the first request after idle takes
  ~30s to wake. Upgrade to a paid instance for always-on.

## Railway (alternative — also uses the Dockerfile)

1. Push to GitHub.
2. On [railway.app](https://railway.app): **New Project → Deploy from GitHub repo**.
3. Railway auto-detects the `Dockerfile` and deploys. It injects `$PORT`, which
   the container already honours.

## Docker (for local testing or self-hosted)

```bash
docker build -t f1fantasy .
docker run -p 8000:8000 f1fantasy
```

Opens at http://localhost:8000 (includes auto-refresh on first boot).

## Local development

```bash
# Terminal 1: API
uv run uvicorn f1fantasy.api:app --port 8000

# Terminal 2: Frontend (Vite dev server)
cd frontend && npm install && npm run dev
```

Frontend at http://localhost:5173 (proxies `/api` to backend).
