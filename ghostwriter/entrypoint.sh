#!/bin/sh
set -e

echo "Running database migrations..."

# Run Alembic migrations
cd /app
alembic upgrade head || {
    echo "Alembic migrations failed or not available, falling back to legacy migrations..."
}

# Legacy migration scripts (for pre-existing databases)
python scripts/migrate_add_article_content.py || true
python scripts/migrate_nullable_feed_id.py || true

echo "Starting Ghostwriter..."
exec python -OO -m uvicorn app.main:app --host 0.0.0.0 --port 8080
