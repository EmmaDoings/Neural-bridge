#!/usr/bin/env bash
set -euo pipefail

echo "Starting Neural Bridge API and web app"

python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

(uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir backend) &

cd frontend
npm install
npm run dev
