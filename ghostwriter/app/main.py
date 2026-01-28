"""FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app import __version__
from app.api.health import set_startup_time
from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging import configure_logging, digest_logger
from app.worker.scheduler import setup_scheduler, shutdown_scheduler

# Configure logging (both standard and digest activity logging)
settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)

# Frontend directory (built SvelteKit app)
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle proxy headers (X-Forwarded-Proto, X-Forwarded-Host).

    This ensures that URL generation (e.g., for OAuth callbacks) uses the
    correct scheme (https) when behind a reverse proxy like Cloudflare or nginx.
    """

    async def dispatch(self, request: Request, call_next):
        # Check for X-Forwarded-Proto header
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto:
            # Update the scope to use the forwarded scheme
            request.scope["scheme"] = forwarded_proto

        # Check for X-Forwarded-Host header
        forwarded_host = request.headers.get("x-forwarded-host")
        if forwarded_host:
            # Update headers to use forwarded host for URL generation
            # This modifies the scope so request.url uses the correct host
            headers = dict(request.scope["headers"])
            headers[b"host"] = forwarded_host.encode()
            request.scope["headers"] = list(headers.items())

        return await call_next(request)


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
    os.makedirs(settings.logs_dir, exist_ok=True)

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

# Proxy headers middleware (for correct URL generation behind reverse proxy)
app.add_middleware(ProxyHeadersMiddleware)

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


# Serve frontend static files if the build directory exists
if FRONTEND_DIR.exists() and (FRONTEND_DIR / "index.html").exists():
    logger.info(f"Serving frontend from {FRONTEND_DIR}")

    # Mount static assets (JS, CSS, images, etc.)
    # These are typically in _app/ for SvelteKit builds
    if (FRONTEND_DIR / "_app").exists():
        app.mount("/_app", StaticFiles(directory=FRONTEND_DIR / "_app"), name="app-assets")

    # Mount any other static files (favicon, robots.txt, etc.)
    # We'll handle index.html separately for SPA routing

    @app.get("/favicon.svg")
    async def favicon():
        """Serve favicon."""
        favicon_path = FRONTEND_DIR / "favicon.svg"
        if favicon_path.exists():
            return FileResponse(favicon_path)
        return FileResponse(FRONTEND_DIR / "favicon.ico")

    @app.get("/robots.txt")
    async def robots():
        """Serve robots.txt."""
        return FileResponse(FRONTEND_DIR / "robots.txt")

    # SPA fallback - catch all frontend routes and serve index.html
    # This must be registered last, after all API routes
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """
        Serve the SPA for any unmatched routes.

        This enables client-side routing - all frontend routes
        return index.html and let SvelteKit handle routing.
        """
        # Don't serve index.html for API paths or known backend paths
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
            return {"detail": "Not found"}

        # Check if it's a direct file request (has extension)
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Otherwise, serve index.html for SPA routing
        return FileResponse(FRONTEND_DIR / "index.html")

else:
    # No frontend build - serve a simple JSON response at root
    @app.get("/")
    async def root():
        """Root endpoint with basic service info."""
        return {
            "service": "Ghostwriter",
            "version": __version__,
            "docs": "/docs",
            "note": "Web UI not built. Run 'npm run build' in frontend/ to enable.",
        }
