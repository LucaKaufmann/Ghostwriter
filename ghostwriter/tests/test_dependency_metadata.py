"""Installation manifest and test isolation regression checks."""

import socket
import tomllib
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings
from app.main import settings as app_settings

ROOT = Path(__file__).resolve().parents[1]


def test_requirements_match_project_dependencies():
    """Docker's standalone requirements path must match package metadata."""
    with (ROOT / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)["project"]
    text = (ROOT / "requirements.txt").read_text()
    lines = text.splitlines()
    marker = next(i for i, line in enumerate(lines) if line.startswith("# Dev/Testing"))
    runtime_text = lines[:marker]
    test_text = lines[marker + 1 :]
    runtime = [line.strip() for line in runtime_text if line.strip() and not line.startswith("#")]
    test = [line.strip() for line in test_text if line.strip() and not line.startswith("#")]
    assert sorted(runtime) == sorted(project["dependencies"])
    assert set(test) <= set(project["optional-dependencies"]["dev"])
    assert len(runtime + test) == len(set(runtime + test))


def test_dotenv_and_host_integrations_do_not_enter_test_settings(tmp_path, monkeypatch):
    """A sentinel .env in the working directory cannot override test settings."""
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sentinel-provider-key\n"
        "GMAIL_CLIENT_SECRET=sentinel-gmail-secret\n"
        "WALLABAG_PASSWORD=sentinel-wallabag-password\n"
        "SCHEDULE_ENABLED=true\n"
        "DATA_DIR=/sentinel-outside-test-data\n"
    )
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.openai_api_key == ""
    assert settings.gmail_client_secret == ""
    assert settings.wallabag_password == ""
    assert not settings.schedule_enabled
    assert settings.data_dir != "/sentinel-outside-test-data"
    assert get_settings().openai_api_key == app_settings.openai_api_key == ""
    assert not app_settings.schedule_enabled


def test_network_requires_explicit_fixtures():
    with pytest.raises(AssertionError, match="mock DNS"):
        socket.getaddrinfo("example.com", 443)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        with pytest.raises(AssertionError, match="mock outbound IP"):
            connection.connect(("93.184.215.14", 443))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        with pytest.raises(AssertionError, match="mock outbound IP"):
            connection.sendto(b"test", ("93.184.215.14", 53))
