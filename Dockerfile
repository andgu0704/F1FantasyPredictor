# --- Stage 1: build the React frontend -------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime ------------------------------------------------
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Install Python deps first for layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY f1fantasy/ ./f1fantasy/
COPY data/ ./data/
COPY --from=frontend /app/frontend/dist ./frontend/dist

# The committed database is baked in, so boot is instant. If it's somehow missing,
# fall back to ingesting. Honour $PORT (Render/Railway set it; default 8000).
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["sh", "-c", "test -f data/f1fantasy.db || python -m f1fantasy.ingestion.ingest; uvicorn f1fantasy.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
