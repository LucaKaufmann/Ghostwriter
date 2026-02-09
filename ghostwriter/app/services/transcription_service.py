"""Unified transcription service: local whisper.cpp and OpenAI Whisper API."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import Settings, get_settings
from app.services.whisper_models import resolve_whisper_model_path

logger = logging.getLogger(__name__)

# OpenAI Whisper API file size limit (25 MB)
_OPENAI_MAX_FILE_SIZE = 25 * 1024 * 1024


@dataclass
class TranscriptionResult:
    """Result of a transcription attempt."""

    text: str
    provider: str  # "local" | "openai"
    duration_seconds: float = 0.0
    error: str | None = None


class TranscriptionService:
    """Transcribe audio via local whisper.cpp or OpenAI Whisper API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _resolve_whisper_binary(self) -> Path | None:
        """Resolve whisper-cli binary path, preferring user override."""
        override_path = (
            Path(os.path.expanduser(self.settings.data_dir)) / "bin" / "whisper-cli"
        )
        if override_path.is_file() and os.access(override_path, os.X_OK):
            return override_path

        configured = self.settings.whisper_cpp_binary.strip()
        if configured:
            configured_path = Path(os.path.expanduser(configured))
            if configured_path.is_file() and os.access(configured_path, os.X_OK):
                return configured_path

        return None

    async def _transcribe_local(
        self, audio_path: str, whisper_model: str, timeout_seconds: int | None = None
    ) -> TranscriptionResult:
        """Transcribe using local whisper.cpp binary."""
        binary = self._resolve_whisper_binary()
        if not binary:
            return TranscriptionResult(
                text="",
                provider="local",
                error="whisper-cli binary not found",
            )

        models_dir = Path(os.path.expanduser(self.settings.whisper_models_dir))
        model_path = resolve_whisper_model_path(models_dir, whisper_model)
        if not model_path:
            return TranscriptionResult(
                text="",
                provider="local",
                error=f"whisper model '{whisper_model}' not found in {models_dir}",
            )

        cmd = [
            str(binary),
            "-m", str(model_path),
            "-f", audio_path,
            "--no-timestamps",
        ]
        effective_timeout = timeout_seconds or self.settings.whisper_transcription_timeout_seconds
        logger.info("Running whisper-cli: %s", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return TranscriptionResult(
                text="",
                provider="local",
                error=f"whisper-cli timed out after {effective_timeout}s",
            )
        except FileNotFoundError:
            return TranscriptionResult(
                text="",
                provider="local",
                error=f"whisper-cli not found at {binary}",
            )

        if process.returncode != 0:
            err_text = stderr.decode("utf-8", errors="ignore").strip()
            return TranscriptionResult(
                text="",
                provider="local",
                error=f"whisper-cli exit {process.returncode}: {err_text[:300]}",
            )

        text = stdout.decode("utf-8", errors="ignore").strip()
        if not text:
            return TranscriptionResult(
                text="", provider="local", error="whisper-cli returned empty output"
            )

        return TranscriptionResult(text=text, provider="local")

    async def _transcribe_openai(self, audio_path: str, timeout_seconds: int | None = None) -> TranscriptionResult:
        """Transcribe using OpenAI Whisper API."""
        api_key = self.settings.openai_api_key
        if not api_key:
            return TranscriptionResult(
                text="",
                provider="openai",
                error="OPENAI_API_KEY not configured",
            )

        file_size = os.path.getsize(audio_path)

        if file_size <= _OPENAI_MAX_FILE_SIZE:
            return await self._openai_transcribe_file(audio_path, api_key, timeout_seconds)

        # File too large — segment into 10-minute WAV chunks
        return await self._openai_transcribe_chunked(audio_path, api_key, timeout_seconds)

    async def _openai_transcribe_file(
        self, audio_path: str, api_key: str, timeout_seconds: int | None = None
    ) -> TranscriptionResult:
        """Send a single file to OpenAI Whisper API."""
        effective_timeout = timeout_seconds or self.settings.openai_whisper_timeout_seconds
        try:
            async with httpx.AsyncClient(
                timeout=effective_timeout
            ) as client:
                with open(audio_path, "rb") as f:
                    response = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        files={"file": (Path(audio_path).name, f, "audio/wav")},
                        data={"model": "whisper-1"},
                    )
                if response.status_code != 200:
                    return TranscriptionResult(
                        text="",
                        provider="openai",
                        error=f"OpenAI API {response.status_code}: {response.text[:300]}",
                    )
                data = response.json()
                return TranscriptionResult(
                    text=data.get("text", ""), provider="openai"
                )
        except httpx.TimeoutException:
            return TranscriptionResult(
                text="",
                provider="openai",
                error=f"OpenAI API timed out after {effective_timeout}s",
            )
        except Exception as e:
            return TranscriptionResult(
                text="", provider="openai", error=f"OpenAI API error: {e!r}"
            )

    async def _openai_transcribe_chunked(
        self, audio_path: str, api_key: str, timeout_seconds: int | None = None
    ) -> TranscriptionResult:
        """Split audio into 10-minute WAV chunks and transcribe each."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chunk_pattern = os.path.join(tmpdir, "chunk_%03d.wav")
            cmd = [
                "ffmpeg", "-i", audio_path,
                "-f", "segment",
                "-segment_time", "600",
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                chunk_pattern,
                "-y", "-loglevel", "error",
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                return TranscriptionResult(
                    text="",
                    provider="openai",
                    error=f"ffmpeg segmentation failed: {stderr.decode()[:300]}",
                )

            chunks = sorted(Path(tmpdir).glob("chunk_*.wav"))
            if not chunks:
                return TranscriptionResult(
                    text="", provider="openai", error="ffmpeg produced no chunks"
                )

            texts: list[str] = []
            for chunk in chunks:
                result = await self._openai_transcribe_file(str(chunk), api_key, timeout_seconds)
                if result.error:
                    return result
                texts.append(result.text)

            return TranscriptionResult(
                text=" ".join(texts), provider="openai"
            )

    async def transcribe(
        self,
        audio_path: str,
        provider: str = "local",
        whisper_model: str = "base.en",
        timeout_seconds: int | None = None,
    ) -> TranscriptionResult:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to the audio file (WAV preferred).
            provider: "local", "openai", or "auto".
            whisper_model: whisper.cpp model name (for local provider).
            timeout_seconds: Override timeout for transcription (applies to both providers).

        Returns:
            TranscriptionResult with transcribed text or error.
        """
        if provider == "local":
            return await self._transcribe_local(audio_path, whisper_model, timeout_seconds)
        elif provider == "openai":
            return await self._transcribe_openai(audio_path, timeout_seconds)
        elif provider == "auto":
            result = await self._transcribe_local(audio_path, whisper_model, timeout_seconds)
            if result.error:
                logger.warning(
                    "Local transcription failed, falling back to OpenAI: %s",
                    result.error,
                )
                return await self._transcribe_openai(audio_path, timeout_seconds)
            return result
        else:
            return TranscriptionResult(
                text="", provider=provider, error=f"Unknown provider: {provider}"
            )
