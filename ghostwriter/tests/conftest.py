import importlib
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATA_DIR", "/tmp/ghostwriter_test_data")
os.environ.setdefault("OUTPUT_DIR", "/tmp/ghostwriter_test_output")
os.environ.setdefault("LOGS_DIR", "/tmp/ghostwriter_test_logs")
os.environ.setdefault("API_KEY", "")
os.environ.setdefault("SCHEDULE_ENABLED", "false")


@pytest.fixture(autouse=True)
def env_setup(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    logs_dir = tmp_path / "logs"

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("LOGS_DIR", str(logs_dir))
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("SCHEDULE_ENABLED", "false")

    import app.core.config as config
    import app.core.database as database
    import app.worker.scheduler as scheduler

    importlib.reload(config)
    importlib.reload(database)
    importlib.reload(scheduler)
    database.init_db()

    yield


@pytest.fixture
def client(env_setup):
    import app.main as main

    importlib.reload(main)

    return TestClient(main.app)
