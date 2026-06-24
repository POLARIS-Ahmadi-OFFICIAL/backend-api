#!/bin/sh
set -e

python init_db.py

PORT="${PORT:-8080}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
