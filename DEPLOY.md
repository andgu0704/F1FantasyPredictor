# Deployment

## Vercel (recommended for this app)

The app runs on Vercel's serverless platform. The database is committed to git, so deployments are zero-config.

### Steps

1. **Install Vercel CLI** (optional, for local testing):
   ```bash
   npm install -g vercel
   ```

2. **Connect to Vercel**:
   ```bash
   vercel link
   ```
   or push to GitHub and connect the repo via vercel.com.

3. **Deploy**:
   ```bash
   vercel deploy
   ```
   or just push to your repo's `main` branch (Vercel auto-deploys).

### How it works

- `vercel.json` tells Vercel to:
  - Build the frontend (React/Vite) into `frontend/dist`
  - Serve `api/index.py` (the FastAPI app) as a serverless function
  - Proxy `/api/*` requests to that function
  - Serve static files (the built UI) for all other routes
- The database (`data/f1fantasy.db`) is committed, so it ships with every deployment.
- Cold starts are fast (~0.5s) because Python + dependencies are cached.

### Notes

- **The `/api/refresh` endpoint** is disabled on Vercel (no persistent filesystem). Update data manually by:
  1. Running locally: `uv run python -m f1fantasy.ingestion.ingest`
  2. Committing the new `data/f1fantasy.db`
  3. Pushing to trigger a redeploy
- For a production app with live data, use a **remote database** (PostgreSQL on Railway, PlanetScale, etc.) and set the `DATABASE_URL` environment variable in Vercel.

## Render (recommended — runs the real container)

The most reliable option: Render builds the `Dockerfile`, so it runs the exact
app that works locally — no serverless constraints (PuLP's solver, read-only FS).

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
