"""Main API router aggregating all endpoints."""

from fastapi import APIRouter

from app.api import digests, feeds, health

api_router = APIRouter()

# Include all route modules
api_router.include_router(health.router, tags=["System"])
api_router.include_router(feeds.router, prefix="/feeds", tags=["Feeds"])
api_router.include_router(digests.router, prefix="/digests", tags=["Digests"])
