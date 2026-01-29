"""Main API router aggregating all endpoints."""

from fastapi import APIRouter

from app.api import auth, client, config, digests, feeds, health, logs, newsletters, schedules, sync

api_router = APIRouter()

# Include all route modules
api_router.include_router(health.router, tags=["System"])
api_router.include_router(sync.router, prefix="/sync", tags=["Sync"])
api_router.include_router(auth.router, tags=["Authentication"])
api_router.include_router(feeds.router, prefix="/feeds", tags=["Feeds"])
api_router.include_router(digests.router, prefix="/digests", tags=["Digests"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["Schedules"])
api_router.include_router(client.router, prefix="/client", tags=["Client"])
api_router.include_router(config.router, prefix="/config", tags=["Config"])
api_router.include_router(newsletters.router, prefix="/newsletters", tags=["Newsletters"])
api_router.include_router(logs.router, prefix="/logs", tags=["Logs"])
