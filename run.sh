#!/bin/bash
cd /Users/andgu0704/F1FantasyPredictor
uv run uvicorn f1fantasy.api:app --port 8000 &
cd frontend && npm run dev -- --port 5173 &
sleep 2 && open http://localhost:5173
echo "App running at http://localhost:5173"
echo "Kill with: pkill -f 'uvicorn|vite'"
