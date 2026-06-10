"""Global pytest fixtures and environment setup for Ghostwriter tests."""

from __future__ import annotations

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

# Use the cheapest bcrypt cost factor so token/password hashing doesn't
# dominate test runtime (~300ms per hash at the production default of 12).
os.environ["BCRYPT_ROUNDS"] = "4"

from app.main import app  # noqa: E402  # env must be set before import


@pytest.fixture
def client():
    """Create a FastAPI TestClient."""
    with TestClient(app) as client:
        yield client
