"""Tests for Summarize.sh service integration."""

from __future__ import annotations

import asyncio
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
