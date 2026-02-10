#!/bin/sh
set -e

echo "Running database migrations..."
cd /app
alembic upgrade head

echo "Starting Ghostwriter..."
exec python -OO -m uvicorn app.main:app --host 0.0.0.0 --port 8080
