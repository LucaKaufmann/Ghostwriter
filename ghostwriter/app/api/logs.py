"""Log file access endpoints."""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


class LogFileInfo(BaseModel):
    """Information about a log file."""

    filename: str
    size_bytes: int
    modified_at: str


@router.get("", response_model=list[LogFileInfo])
async def list_log_files() -> list[LogFileInfo]:
    """List available log files, newest first."""
    settings = get_settings()
    logs_dir = Path(settings.logs_dir)

    if not logs_dir.exists():
        return []

    files = []
    for f in sorted(logs_dir.glob("ghostwriter*.log*"), reverse=True):
        if f.is_file():
            stat = f.stat()
            files.append(
                LogFileInfo(
                    filename=f.name,
                    size_bytes=stat.st_size,
                    modified_at=str(stat.st_mtime),
                )
            )

    return files


@router.get("/{filename}")
async def download_log_file(filename: str):
    """Download a specific log file."""
    # Sanitize filename to prevent path traversal
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    settings = get_settings()
    file_path = Path(settings.logs_dir) / safe_name

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log file not found",
        )

    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type="text/plain",
    )
