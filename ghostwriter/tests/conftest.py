"""Pytest configuration for Ghostwriter.

The application defaults to container paths like /app/data and /app/logs.
When running tests locally those paths may be unwritable or not exist, so we
force them to a temporary writable directory before the app is imported.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="ghostwriter-tests-"))

os.environ.setdefault("DATA_DIR", str(_TEST_ROOT / "data"))
os.environ.setdefault("OUTPUT_DIR", str(_TEST_ROOT / "output"))
os.environ.setdefault("LOGS_DIR", str(_TEST_ROOT / "logs"))

Path(os.environ["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["OUTPUT_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["LOGS_DIR"]).mkdir(parents=True, exist_ok=True)

