"""Main API router aggregating all endpoints."""

from fastapi import APIRouter

from app.api import client, digests, feeds, health, schedules

api_router = APIRouter()

# Include all route modules
api_router.include_router(health.router, tags=["System"])
api_router.include_router(feeds.router, prefix="/feeds", tags=["Feeds"])
api_router.include_router(digests.router, prefix="/digests", tags=["Digests"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["Schedules"])
api_router.include_router(client.router, prefix="/client", tags=["Client"])
