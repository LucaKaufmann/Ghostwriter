"""Global pytest fixtures and environment setup for Ghostwriter tests."""

from __future__ import annotations

import ipaddress
import os
import socket
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings

# Configure tests before importing the app, which caches settings at import time.
# Do not read a developer's or deployment's .env, even when pytest starts there.
_original_environment = dict(os.environ)
_original_model_config = Settings.model_config
Settings.model_config = {**Settings.model_config, "env_file": None}
for field in Settings.model_fields:
    os.environ.pop(field.upper(), None)
for name in tuple(os.environ):
    if name.startswith(("OPENAI_", "ANTHROPIC_", "GEMINI_", "ELEVENLABS_", "LITELLM_")):
        os.environ.pop(name, None)

_BASE_DIR = tempfile.mkdtemp(prefix="ghostwriter_test_")
os.environ.update(
    DATA_DIR=os.path.join(_BASE_DIR, "data"),
    OUTPUT_DIR=os.path.join(_BASE_DIR, "output"),
    LOGS_DIR=os.path.join(_BASE_DIR, "logs"),
    API_KEY="",
    JWT_SECRET="test-only-secret",
    OPENAI_API_KEY="",
    GEMINI_API_KEY="",
    WEBHOOK_URL="",
    WALLABAG_URL="",
    WALLABAG_CLIENT_ID="",
    WALLABAG_CLIENT_SECRET="",
    WALLABAG_USERNAME="",
    WALLABAG_PASSWORD="",
    GMAIL_CLIENT_ID="",
    GMAIL_CLIENT_SECRET="",
    SCHEDULE_ENABLED="false",
    LITELLM_MODE="PRODUCTION",
    LITELLM_LOCAL_MODEL_COST_MAP="true",
    BCRYPT_ROUNDS="4",
)
get_settings.cache_clear()

# Install the network guard before app imports and test module collection. Tests
# can replace individual socket functions with explicit fixtures or mocks.
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_sendto = socket.socket.sendto
_original_sendmsg = getattr(socket.socket, "sendmsg", None)
_original_dns = {
    "getaddrinfo": socket.getaddrinfo,
    "gethostbyname": socket.gethostbyname,
    "gethostbyname_ex": socket.gethostbyname_ex,
    "gethostbyaddr": socket.gethostbyaddr,
    "getnameinfo": socket.getnameinfo,
}


def _blocked_dns(host, port=None, *_args, **_kwargs):
    # The current URL validator passes IP literals to getaddrinfo after its
    # first rejection path. Echo literals without consulting a resolver so
    # its existing private-address checks still run.
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (host, port))]
    raise AssertionError("Tests must mock DNS resolution")


def _deny_dns(*_args, **_kwargs):
    raise AssertionError("Tests must mock DNS resolution")


def _blocked_connect(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        raise AssertionError("Tests must mock outbound IP connections")
    return _original_connect(sock, address)


def _blocked_connect_ex(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        raise AssertionError("Tests must mock outbound IP connections")
    return _original_connect_ex(sock, address)


def _blocked_sendto(sock, *args):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        raise AssertionError("Tests must mock outbound IP connections")
    return _original_sendto(sock, *args)


def _blocked_sendmsg(sock, *args):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        raise AssertionError("Tests must mock outbound IP connections")
    return _original_sendmsg(sock, *args)


socket.getaddrinfo = _blocked_dns
socket.gethostbyname = _deny_dns
socket.gethostbyname_ex = _deny_dns
socket.gethostbyaddr = _deny_dns
socket.getnameinfo = _deny_dns
socket.socket.connect = _blocked_connect
socket.socket.connect_ex = _blocked_connect_ex
socket.socket.sendto = _blocked_sendto
if _original_sendmsg is not None:
    socket.socket.sendmsg = _blocked_sendmsg


def _restore_host_state():
    os.environ.clear()
    os.environ.update(_original_environment)
    Settings.model_config = _original_model_config
    get_settings.cache_clear()
    for name, function in _original_dns.items():
        setattr(socket, name, function)
    socket.socket.connect = _original_connect
    socket.socket.connect_ex = _original_connect_ex
    socket.socket.sendto = _original_sendto
    if _original_sendmsg is not None:
        socket.socket.sendmsg = _original_sendmsg


try:
    from app.main import app  # noqa: E402  # environment must be set before import
except BaseException:
    _restore_host_state()
    raise


def pytest_unconfigure(config):
    """Leave an embedding process as it was before pytest loaded conftest."""
    _restore_host_state()


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch):
    """Require explicit mocks for DNS and outbound IP connections."""
    monkeypatch.setattr(socket, "getaddrinfo", _blocked_dns)
    monkeypatch.setattr(socket, "gethostbyname", _deny_dns)
    monkeypatch.setattr(socket, "gethostbyname_ex", _deny_dns)
    monkeypatch.setattr(socket, "gethostbyaddr", _deny_dns)
    monkeypatch.setattr(socket, "getnameinfo", _deny_dns)
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked_connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", _blocked_sendto)
    if _original_sendmsg is not None:
        monkeypatch.setattr(socket.socket, "sendmsg", _blocked_sendmsg)


@pytest.fixture
def client():
    """Create a FastAPI TestClient."""
    with TestClient(app) as client:
        yield client
