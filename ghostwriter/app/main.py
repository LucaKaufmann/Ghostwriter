"""FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.health import set_startup_time
from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import init_db
from app.worker.scheduler import setup_scheduler, shutdown_scheduler

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Manages startup and shutdown tasks including database initialization
    and scheduler setup/teardown.
    """
    # Startup
    logger.info(f"Starting Ghostwriter v{__version__}")

    # Ensure directories exist
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(settings.output_dir, exist_ok=True)

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Track startup time
    set_startup_time(datetime.utcnow())

    # Start scheduler
    setup_scheduler()

    yield

    # Shutdown
    logger.info("Shutting down Ghostwriter")
    shutdown_scheduler()


# Create FastAPI app
app = FastAPI(
    title="Ghostwriter",
    description="RSS digest generation service for Epilogue",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware (for development/debugging)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.get("/")
async def root():
    """Root endpoint with basic service info."""
    return {
        "service": "Ghostwriter",
        "version": __version__,
        "docs": "/docs",
    }
