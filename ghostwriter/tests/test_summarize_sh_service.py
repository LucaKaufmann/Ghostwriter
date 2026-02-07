"""Tests for Summarize.sh service integration."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.summarize_sh_service import SummarizeShService


class DummyProcess:
    """Minimal subprocess stub for SummarizeShService tests."""

    def __init__(self, stdout: bytes, stderr: bytes, returncode: int) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def _service_with_config(tmp_path: Path) -> SummarizeShService:
    config_path = tmp_path / "summarize.json"
    config_path.write_text("{}\n", encoding="utf-8")
    settings = Settings(summarize_sh_config_path=str(config_path))
    return SummarizeShService(settings)


def _service_with_settings(tmp_path: Path, **overrides) -> SummarizeShService:
    config_path = tmp_path / "summarize.json"
    config_path.write_text("{}\n", encoding="utf-8")
    settings = Settings(summarize_sh_config_path=str(config_path), **overrides)
    return SummarizeShService(settings)


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    path.chmod(0o755)


def test_build_env_prefers_data_volume_whisper_override(tmp_path, caplog):
    data_dir = tmp_path / "data"
    override_path = data_dir / "bin" / "whisper-cli"
    _make_executable(override_path)

    bundled_path = tmp_path / "bundled-whisper-cli"
    _make_executable(bundled_path)

    service = _service_with_settings(
        tmp_path,
        data_dir=str(data_dir),
        summarize_sh_whisper_cpp_binary=str(bundled_path),
    )

    caplog.set_level(logging.INFO, logger="app.services.summarize_sh_service")
    env = service._build_env(whisper_model=None, cli_home=None)

    assert env["SUMMARIZE_WHISPER_CPP_BINARY"] == str(override_path)
    assert f"Whisper binary resolved: {override_path} (user override)" in caplog.text


def test_build_env_falls_back_to_configured_binary(tmp_path):
    data_dir = tmp_path / "data"
    bundled_path = tmp_path / "bundled-whisper-cli"
    _make_executable(bundled_path)

    service = _service_with_settings(
        tmp_path,
        data_dir=str(data_dir),
        summarize_sh_whisper_cpp_binary=str(bundled_path),
    )

    env = service._build_env(whisper_model=None, cli_home=None)

    assert env["SUMMARIZE_WHISPER_CPP_BINARY"] == str(bundled_path)


def test_build_env_skips_non_executable_override_and_uses_configured_binary(
    tmp_path, caplog
):
    data_dir = tmp_path / "data"
    override_path = data_dir / "bin" / "whisper-cli"
    override_path.parent.mkdir(parents=True, exist_ok=True)
    override_path.write_text("not executable\n", encoding="utf-8")
    override_path.chmod(0o644)

    bundled_path = tmp_path / "bundled-whisper-cli"
    _make_executable(bundled_path)

    service = _service_with_settings(
        tmp_path,
        data_dir=str(data_dir),
        summarize_sh_whisper_cpp_binary=str(bundled_path),
    )

    caplog.set_level(logging.WARNING, logger="app.services.summarize_sh_service")
    env = service._build_env(whisper_model=None, cli_home=None)

    assert env["SUMMARIZE_WHISPER_CPP_BINARY"] == str(bundled_path)
    assert "Whisper override binary exists but is not executable" in caplog.text


def test_build_env_unsets_whisper_binary_when_missing(tmp_path, monkeypatch):
    service = _service_with_settings(
        tmp_path,
        data_dir=str(tmp_path / "data"),
        summarize_sh_whisper_cpp_binary=str(tmp_path / "does-not-exist"),
    )
    monkeypatch.setenv("SUMMARIZE_WHISPER_CPP_BINARY", "stale-value")

    env = service._build_env(whisper_model=None, cli_home=None)

    assert "SUMMARIZE_WHISPER_CPP_BINARY" not in env


def test_summarize_sh_missing_cli_sets_error(monkeypatch, tmp_path):
    service = _service_with_config(tmp_path)

    async def _raise(*_args, **_kwargs):
        raise FileNotFoundError("summarize")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _raise)

    result = asyncio.run(service.summarize_url("https://example.com"))

    assert result.ai_failed is True
    assert result.error == "summarize CLI not found in PATH"


def test_summarize_sh_nonzero_exit_includes_stderr(monkeypatch, tmp_path):
    service = _service_with_config(tmp_path)

    async def _proc(*_args, **_kwargs):
        return DummyProcess(b"", b"error:\n  bad input\n", 2)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _proc)

    result = asyncio.run(service.summarize_url("https://example.com"))

    assert result.ai_failed is True
    assert result.error == "exit 2: error: bad input"


def test_summarize_sh_empty_output_sets_error(monkeypatch, tmp_path):
    service = _service_with_config(tmp_path)

    async def _proc(*_args, **_kwargs):
        return DummyProcess(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _proc)

    result = asyncio.run(service.summarize_url("https://example.com"))

    assert result.ai_failed is True
    assert result.error == "empty output"
