"""whisper.cpp model download and management."""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.core.config import Settings, get_settings
from app.services.whisper_models import WHISPER_MODELS, list_whisper_models


@dataclass
class DownloadStatus:
    status: str
    bytes_downloaded: int
    total_bytes: int | None
    error: str | None
    updated_at: datetime


_STATUS_LOCK = Lock()
_DOWNLOAD_STATUS: dict[str, DownloadStatus] = {}


class WhisperModelService:
    """Manage whisper.cpp models on disk."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.models_dir = Path(
            os.path.expanduser(self.settings.whisper_models_dir)
        )

    def list_models(self) -> list[dict]:
        """List available models and their local status."""
        statuses = self._status_snapshot()
        models = []
        for model in list_whisper_models():
            path = self.models_dir / model.filename
            downloaded = path.exists()
            size_bytes = path.stat().st_size if downloaded else None

            status = "downloaded" if downloaded else "not_downloaded"
            bytes_downloaded = None
            total_bytes = None
            error = None

            status_entry = statuses.get(model.name)
            if status_entry:
                if status_entry.status == "downloading":
                    status = "downloading"
                elif status_entry.status == "failed" and not downloaded:
                    status = "failed"
                bytes_downloaded = status_entry.bytes_downloaded
                total_bytes = status_entry.total_bytes
                error = status_entry.error

            models.append(
                {
                    "name": model.name,
                    "filename": model.filename,
                    "downloaded": downloaded,
                    "size_bytes": size_bytes,
                    "status": status,
                    "bytes_downloaded": bytes_downloaded,
                    "total_bytes": total_bytes,
                    "error": error,
                }
            )
        return models

    def is_downloaded(self, model_name: str) -> bool:
        """Check if a model is downloaded."""
        model = WHISPER_MODELS.get(model_name)
        if not model:
            return False
        return (self.models_dir / model.filename).exists()

    def is_downloading(self, model_name: str) -> bool:
        """Check if a model download is in progress."""
        with _STATUS_LOCK:
            status = _DOWNLOAD_STATUS.get(model_name)
            return status is not None and status.status == "downloading"

    def download_model(self, model_name: str) -> None:
        """Download a whisper.cpp model to the models directory."""
        model = WHISPER_MODELS.get(model_name)
        if not model:
            raise ValueError("Unknown model")

        self.models_dir.mkdir(parents=True, exist_ok=True)
        target_path = self.models_dir / model.filename
        if target_path.exists():
            self._clear_status(model_name)
            return

        with _STATUS_LOCK:
            existing = _DOWNLOAD_STATUS.get(model_name)
            if existing and existing.status == "downloading":
                raise RuntimeError("Download already in progress")
            _DOWNLOAD_STATUS[model_name] = DownloadStatus(
                status="downloading",
                bytes_downloaded=0,
                total_bytes=None,
                error=None,
                updated_at=datetime.now(timezone.utc),
            )

        tmp_path = target_path.with_suffix(".download")
        if tmp_path.exists():
            tmp_path.unlink()

        bytes_downloaded = 0
        try:
            with urllib.request.urlopen(model.url) as response:
                total_header = response.headers.get("Content-Length")
                total_bytes = int(total_header) if total_header and total_header.isdigit() else None
                self._update_status(model_name, bytes_downloaded, total_bytes)

                with open(tmp_path, "wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        bytes_downloaded += len(chunk)
                        self._update_status(model_name, bytes_downloaded, total_bytes)

            tmp_path.replace(target_path)
            self._clear_status(model_name)
        except Exception as exc:
            if tmp_path.exists():
                tmp_path.unlink()
            self._set_failed(model_name, str(exc))
            raise

    def delete_model(self, model_name: str) -> bool:
        """Delete a downloaded model."""
        model = WHISPER_MODELS.get(model_name)
        if not model:
            raise ValueError("Unknown model")

        with _STATUS_LOCK:
            status = _DOWNLOAD_STATUS.get(model_name)
            if status and status.status == "downloading":
                raise RuntimeError("Download in progress")

        path = self.models_dir / model.filename
        if path.exists():
            path.unlink()
            return True
        return False

    def _status_snapshot(self) -> dict[str, DownloadStatus]:
        with _STATUS_LOCK:
            return {key: value for key, value in _DOWNLOAD_STATUS.items()}

    def _update_status(
        self, model_name: str, bytes_downloaded: int, total_bytes: int | None
    ) -> None:
        with _STATUS_LOCK:
            status = _DOWNLOAD_STATUS.get(model_name)
            if not status:
                return
            status.bytes_downloaded = bytes_downloaded
            status.total_bytes = total_bytes
            status.updated_at = datetime.now(timezone.utc)

    def _set_failed(self, model_name: str, error: str) -> None:
        with _STATUS_LOCK:
            _DOWNLOAD_STATUS[model_name] = DownloadStatus(
                status="failed",
                bytes_downloaded=0,
                total_bytes=None,
                error=error,
                updated_at=datetime.now(timezone.utc),
            )

    def _clear_status(self, model_name: str) -> None:
        with _STATUS_LOCK:
            _DOWNLOAD_STATUS.pop(model_name, None)
