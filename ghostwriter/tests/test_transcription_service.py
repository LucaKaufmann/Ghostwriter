"""Tests for TranscriptionService."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.transcription_service import TranscriptionService, TranscriptionResult


@pytest.fixture
def settings():
    """Minimal settings mock."""
    s = MagicMock()
    s.whisper_cpp_binary = "/usr/local/bin/whisper-cli"
    s.whisper_models_dir = "/tmp/models"
    s.whisper_transcription_timeout_seconds = 300
    s.openai_whisper_timeout_seconds = 120
    s.openai_api_key = "sk-test"
    s.data_dir = "/app/data"
    return s


@pytest.fixture
def service(settings):
    return TranscriptionService(settings)


@pytest.mark.asyncio
async def test_transcribe_local_success(service):
    """Local transcription returns text on success."""
    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(return_value=(b"Hello world", b""))
    mock_process.returncode = 0

    with (
        patch.object(service, "_resolve_whisper_binary", return_value=MagicMock()),
        patch("app.services.transcription_service.resolve_whisper_model_path", return_value=MagicMock()),
        patch("asyncio.create_subprocess_exec", return_value=mock_process),
        patch("asyncio.wait_for", return_value=(b"Hello world", b"")),
    ):
        # Patch communicate to work with wait_for
        mock_process.communicate = AsyncMock(return_value=(b"Hello world", b""))
        result = await service._transcribe_local("/tmp/audio.wav", "base.en")

    assert result.provider == "local"
    assert result.text == "Hello world"
    assert result.error is None


@pytest.mark.asyncio
async def test_transcribe_local_binary_not_found(service):
    """Local transcription returns error if binary not found."""
    with patch.object(service, "_resolve_whisper_binary", return_value=None):
        result = await service._transcribe_local("/tmp/audio.wav", "base.en")

    assert result.error is not None
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_transcribe_local_model_not_found(service):
    """Local transcription returns error if model not found."""
    with (
        patch.object(service, "_resolve_whisper_binary", return_value=MagicMock()),
        patch("app.services.transcription_service.resolve_whisper_model_path", return_value=None),
    ):
        result = await service._transcribe_local("/tmp/audio.wav", "missing.en")

    assert result.error is not None
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_transcribe_local_timeout(service):
    """Local transcription returns error on timeout."""
    mock_process = AsyncMock()
    mock_process.kill = MagicMock()
    mock_process.communicate = AsyncMock(return_value=(b"", b""))

    with (
        patch.object(service, "_resolve_whisper_binary", return_value=MagicMock()),
        patch("app.services.transcription_service.resolve_whisper_model_path", return_value=MagicMock()),
        patch("asyncio.create_subprocess_exec", return_value=mock_process),
        patch("asyncio.wait_for", side_effect=asyncio.TimeoutError),
    ):
        result = await service._transcribe_local("/tmp/audio.wav", "base.en")

    assert result.error is not None
    assert "timed out" in result.error


@pytest.mark.asyncio
async def test_transcribe_openai_no_key(service):
    """OpenAI transcription returns error if no API key."""
    service.settings.openai_api_key = ""
    result = await service._transcribe_openai("/tmp/audio.wav")

    assert result.error is not None
    assert "not configured" in result.error


@pytest.mark.asyncio
async def test_transcribe_auto_fallback(service):
    """Auto provider falls back to OpenAI when local fails."""
    local_error = TranscriptionResult(text="", provider="local", error="binary not found")
    openai_success = TranscriptionResult(text="transcribed text", provider="openai")

    with (
        patch.object(service, "_transcribe_local", return_value=local_error),
        patch.object(service, "_transcribe_openai", return_value=openai_success),
    ):
        result = await service.transcribe("/tmp/audio.wav", provider="auto")

    assert result.provider == "openai"
    assert result.text == "transcribed text"


@pytest.mark.asyncio
async def test_transcribe_auto_local_success(service):
    """Auto provider uses local result when it succeeds."""
    local_success = TranscriptionResult(text="local text", provider="local")

    with patch.object(service, "_transcribe_local", return_value=local_success):
        result = await service.transcribe("/tmp/audio.wav", provider="auto")

    assert result.provider == "local"
    assert result.text == "local text"


@pytest.mark.asyncio
async def test_transcribe_unknown_provider(service):
    """Unknown provider returns error."""
    result = await service.transcribe("/tmp/audio.wav", provider="invalid")
    assert result.error is not None
    assert "Unknown provider" in result.error
