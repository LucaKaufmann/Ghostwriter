"""Global pytest fixtures and environment setup for Ghostwriter tests."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Configure writable directories for tests before importing the FastAPI app.
_BASE_DIR = tempfile.mkdtemp(prefix="ghostwriter_test_")
os.environ["DATA_DIR"] = os.path.join(_BASE_DIR, "data")
os.environ["OUTPUT_DIR"] = os.path.join(_BASE_DIR, "output")
os.environ["LOGS_DIR"] = os.path.join(_BASE_DIR, "logs")

# Disable auth for tests (setup-mode behavior).
os.environ["API_KEY"] = ""

# Avoid starting background schedulers during tests.
os.environ["SCHEDULE_ENABLED"] = "false"

from app.main import app


@pytest.fixture
def client():
    """Create a FastAPI TestClient."""
    with TestClient(app) as client:
        yield client
