"""Installation manifest and test isolation regression checks."""

import os
import socket
import subprocess
import sys
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
        if hasattr(connection, "sendmsg"):
            with pytest.raises(AssertionError, match="mock outbound IP"):
                connection.sendmsg([b"test"], [], 0, ("93.184.215.14", 53))


def test_host_case_variant_settings_are_isolated():
    assert not app_settings.allow_private_hosts
    assert app_settings.openai_api_key == ""
    assert not app_settings.schedule_enabled
    assert all(name.casefold() != "allow_private_hosts" for name in os.environ)
    controlled = {"openai_api_key", "wallabag_password"}
    assert all(
        name.isupper() or name.casefold() not in controlled
        for name in os.environ
    )


def test_embedded_pytest_restores_host_process(tmp_path):
    """Running pytest.main must not leave its host's env or sockets patched."""
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sentinel-dotenv\n")
    code = f"""
import os
import socket
import pytest
from app.core.config import Settings, get_settings

os.environ["SCHEDULE_ENABLED"] = "true"
os.environ["allow_private_hosts"] = "true"
os.environ["oPeNaI_aPi_KeY"] = "sentinel-mixed-provider"
os.environ["wAlLaBaG_pAsSwOrD"] = "sentinel-mixed-wallabag"
original_env = dict(os.environ)
original_model_config = Settings.model_config
original_socket = {{name: getattr(socket, name) for name in (
    "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"
)}}
original_methods = {{name: getattr(socket.socket, name, None) for name in (
    "connect", "connect_ex", "sendto", "sendmsg"
)}}
assert pytest.main(["-q", "-c", {str(ROOT / 'pyproject.toml')!r},
                    {str(ROOT / 'tests/test_dependency_metadata.py')!r} +
                    "::test_host_case_variant_settings_are_isolated"]) == 0
assert os.environ == original_env
assert Settings.model_config is original_model_config
for name, function in original_socket.items():
    assert getattr(socket, name) is function
for name, function in original_methods.items():
    assert getattr(socket.socket, name, None) is function
assert get_settings().openai_api_key == "sentinel-mixed-provider"
assert get_settings().schedule_enabled
assert get_settings().allow_private_hosts
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
