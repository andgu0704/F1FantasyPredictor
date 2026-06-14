"""Vercel entrypoint for FastAPI app (serverless)."""
from f1fantasy.api import app

__all__ = ["app"]
