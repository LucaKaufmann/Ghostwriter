"""Shared whisper.cpp model metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WhisperModel:
    """Metadata for a whisper.cpp model."""

    name: str
    filename: str
    url: str


_WHISPER_MODEL_ORDER = ("tiny.en", "base.en", "small.en")

WHISPER_MODELS: dict[str, WhisperModel] = {
    "tiny.en": WhisperModel(
        name="tiny.en",
        filename="ggml-tiny.en.bin",
        url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin",
    ),
    "base.en": WhisperModel(
        name="base.en",
        filename="ggml-base.en.bin",
        url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin",
    ),
    "small.en": WhisperModel(
        name="small.en",
        filename="ggml-small.en.bin",
        url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin",
    ),
}


def list_whisper_models() -> list[WhisperModel]:
    """Return whisper models in display order."""
    return [WHISPER_MODELS[name] for name in _WHISPER_MODEL_ORDER]


def resolve_whisper_model_path(models_dir: Path, model_name: str | None) -> Path | None:
    """Resolve a model path if it exists on disk."""
    if not model_name:
        return None
    model = WHISPER_MODELS.get(model_name)
    if not model:
        return None
    path = models_dir / model.filename
    return path if path.exists() else None
