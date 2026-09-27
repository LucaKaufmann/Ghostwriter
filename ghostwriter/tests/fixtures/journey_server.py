"""Run a disposable FastAPI fixture for the real-browser journey spec."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="ghostwriter_journey_"))
    from app.core.config import Settings, get_settings

    Settings.model_config = {**Settings.model_config, "env_file": None}
    setting_names = {name.upper() for name in Settings.model_fields}
    for name in tuple(os.environ):
        upper = name.upper()
        if upper in setting_names or upper.startswith(
            ("OPENAI_", "ANTHROPIC_", "GEMINI_", "ELEVENLABS_", "LITELLM_")
        ) or upper in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}:
            os.environ.pop(name, None)
    os.environ.update(
        DATA_DIR=str(root / "data"),
        OUTPUT_DIR=str(root / "output"),
        LOGS_DIR=str(root / "logs"),
        JWT_SECRET="journey-test-only-secret",
        API_KEY="",
        SCHEDULE_ENABLED="false",
        FETCH_DELAY_MS="0",
        BCRYPT_ROUNDS="4",
        ALLOW_PRIVATE_HOSTS="true",
        OPENAI_API_KEY="",
        LITELLM_MODE="PRODUCTION",
        LITELLM_LOCAL_MODEL_COST_MAP="true",
        NO_PROXY="127.0.0.1,localhost,::1",
    )
    get_settings.cache_clear()

    # Install before importing the app or any provider/source module.
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_sendto = socket.socket.sendto
    original_sendmsg = getattr(socket.socket, "sendmsg", None)
    original_dns = socket.getaddrinfo

    def permitted(host):
        return host in ("127.0.0.1", "::1", "localhost")

    def local_address(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            if not isinstance(address, tuple) or not permitted(address[0]):
                raise AssertionError("Journey fixture forbids external network")

    def local_connect(sock, address):
        local_address(sock, address)
        return original_connect(sock, address)

    def local_connect_ex(sock, address):
        local_address(sock, address)
        return original_connect_ex(sock, address)

    def local_sendto(sock, *args, **kwargs):
        local_address(sock, kwargs.get("address", args[-1] if args else None))
        return original_sendto(sock, *args, **kwargs)

    def local_sendmsg(sock, *args, **kwargs):
        address = kwargs.get("address", args[3] if len(args) > 3 else None)
        local_address(sock, address)
        return original_sendmsg(sock, *args, **kwargs)

    def local_dns(host, *args, **kwargs):
        if not permitted(host):
            raise AssertionError("Journey fixture forbids external DNS")
        return original_dns(host, *args, **kwargs)

    def local_hostbyname(host):
        if not permitted(host):
            raise AssertionError("Journey fixture forbids external DNS")
        return "::1" if host == "::1" else "127.0.0.1"

    def local_hostbyname_ex(host):
        address = local_hostbyname(host)
        return ("localhost", [], [address])

    def local_hostbyaddr(host):
        address = local_hostbyname(host)
        return ("localhost", [], [address])

    def local_nameinfo(address, _flags):
        if not isinstance(address, tuple) or not permitted(address[0]):
            raise AssertionError("Journey fixture forbids external DNS")
        return (address[0], str(address[1]))

    socket.socket.connect = local_connect
    socket.socket.connect_ex = local_connect_ex
    socket.socket.sendto = local_sendto
    if original_sendmsg is not None:
        socket.socket.sendmsg = local_sendmsg
    socket.getaddrinfo = local_dns
    socket.gethostbyname = local_hostbyname
    socket.gethostbyname_ex = local_hostbyname_ex
    socket.gethostbyaddr = local_hostbyaddr
    socket.getnameinfo = local_nameinfo

    import uvicorn
    from fastapi.responses import HTMLResponse
    from pytest import MonkeyPatch

    from app.core.database import init_db
    from app.main import app
    from tests.fixtures.journey_harness import ARTICLE_TEXT, ARTICLE_TITLE, install

    (root / "output").mkdir()
    init_db()
    patches = MonkeyPatch()
    @app.get("/fixture-article", response_class=HTMLResponse)
    def fixture_article():
        return f"<html><head><title>{ARTICLE_TITLE}</title></head><body><article><h1>{ARTICLE_TITLE}</h1><p>{ARTICLE_TEXT}</p></article></body></html>"
    app.router.routes.insert(0, app.router.routes.pop())

    install(
        patches,
        root / "output",
        article_url=f"http://127.0.0.1:{args.port}/fixture-article",
    )

    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
