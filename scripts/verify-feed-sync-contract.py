#!/usr/bin/env python3
"""Run the opt-in Ktor/FastAPI feed contract against disposable loopback SQLite."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_NAME = "com.example.epilogue.shared.sync.FeedSyncV2LiveContractTest"
RESULT = ROOT / "shared/build/test-results/testDebugUnitTest" / f"TEST-{TEST_NAME}.xml"


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)


def wait_until_ready(process: subprocess.Popen[bytes], url: str, log: Path) -> None:
    deadline = time.monotonic() + 30
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Fixture exited early ({process.returncode}):\n{log.read_text()}")
        try:
            with opener.open(f"{url}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Fixture did not become ready in 30 seconds:\n{log.read_text()}")


def verify_result() -> None:
    if not RESULT.is_file():
        raise RuntimeError(f"Dedicated live test produced no result XML: {RESULT}")
    suite = ET.parse(RESULT).getroot()
    tests = int(suite.attrib.get("tests", "0"))
    skipped = int(suite.attrib.get("skipped", "0"))
    failures = int(suite.attrib.get("failures", "0"))
    errors = int(suite.attrib.get("errors", "0"))
    if tests != 1 or skipped or failures or errors:
        raise RuntimeError(
            f"Live contract did not execute cleanly: tests={tests}, "
            f"skipped={skipped}, failures={failures}, errors={errors}"
        )
    print(f"Live contract executed: {tests} test, no skips or failures")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", required=True, type=Path,
        help="Python executable in an installed Ghostwriter fixture environment",
    )
    args = parser.parse_args()
    # Keep the venv executable path: resolving its symlink would lose pyvenv.cfg.
    python = args.python.absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        parser.error("--python must name an executable fixture Python")

    port = free_loopback_port()
    url = f"http://127.0.0.1:{port}"
    fixture = ROOT / "ghostwriter/tests/fixtures/journey_server.py"
    with tempfile.TemporaryDirectory(prefix="epilogue_sync_contract_") as scratch:
        log = Path(scratch) / "fixture.log"
        with log.open("wb") as output:
            fixture_env = os.environ.copy()
            fixture_env["PYTHONPATH"] = str(ROOT / "ghostwriter")
            process = subprocess.Popen(
                [str(python), str(fixture), "--port", str(port)],
                cwd=ROOT / "ghostwriter",
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=fixture_env,
            )
            try:
                wait_until_ready(process, url, log)
                RESULT.unlink(missing_ok=True)
                env = os.environ.copy()
                env["FEED_SYNC_LIVE_URL"] = url
                env["NO_PROXY"] = "127.0.0.1,localhost,::1"
                env["no_proxy"] = env["NO_PROXY"]
                command = [
                    str(ROOT / "gradlew"), ":shared:testDebugUnitTest",
                    "--tests", TEST_NAME, "--rerun-tasks", "--no-daemon",
                ]
                gradle = subprocess.Popen(command, cwd=ROOT, env=env,
                                          start_new_session=True)
                try:
                    try:
                        status = gradle.wait(timeout=720)
                    except subprocess.TimeoutExpired as exc:
                        raise RuntimeError("Live Gradle test exceeded 12 minutes") from exc
                    if status:
                        raise RuntimeError(f"Live Gradle test failed ({status})")
                finally:
                    stop_process_group(gradle)
                verify_result()
            except Exception:
                output.flush()
                print(log.read_text(errors="replace"), file=sys.stderr)
                raise
            finally:
                stop_process_group(process)
                if process.poll() is None:
                    raise RuntimeError("Fixture process survived cleanup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
