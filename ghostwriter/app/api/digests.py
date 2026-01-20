"""Digest management and download endpoints."""

import os
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.security import verify_api_key
from app.models.digest import Digest, DigestRead, DigestStatus
from app.worker.bindery import generate_digest

router = APIRouter()


class TriggerRequest(BaseModel):
    """Request to manually trigger a digest."""

    period: Literal["morning", "noon", "evening", "manual"] = "manual"


class TriggerResponse(BaseModel):
    """Response from digest trigger."""

    id: UUID | None
    status: str
    message: str


class DigestProgress(BaseModel):
    """Progress information for a digest."""

    total_feeds: int
    feeds_fetched: int
    total_articles: int
    articles_enriched: int


class DigestStatusResponse(BaseModel):
    """Detailed status response for a digest job."""

    id: UUID
    status: str
    stage: str | None
    progress: DigestProgress
    started_at: datetime
    eta_seconds: int | None = None


class NewDigestsResponse(BaseModel):
    """Response for checking new digests."""

    has_new: bool
    count: int
    digests: list[DigestRead]


@router.post("/trigger", response_model=TriggerResponse, dependencies=[Depends(verify_api_key)])
async def trigger_digest(
    request: TriggerRequest,
) -> TriggerResponse:
    """
    Manually trigger a digest generation.

    Returns 409 Conflict if a job is already running.
    """
    digest_id = await generate_digest(request.period)

    if digest_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A digest job is already running. Please wait for it to complete.",
        )

    return TriggerResponse(
        id=digest_id,
        status="started",
        message=f"Digest generation started for period: {request.period}",
    )


@router.get("", response_model=list[DigestRead], dependencies=[Depends(verify_api_key)])
async def list_digests(
    session: Session = Depends(get_session),
    limit: int = 20,
    offset: int = 0,
    since: datetime | None = Query(default=None, description="Filter digests created after this datetime (UTC)"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status (completed, failed, processing)"),
    period: str | None = Query(default=None, description="Filter by period (morning, noon, evening, manual)"),
) -> list[Digest]:
    """
    List available digests.

    Returns digests ordered by creation date, newest first.
    Supports filtering by creation date, status, and period.
    """
    statement = select(Digest)

    # Apply filters
    if since:
        statement = statement.where(Digest.created_at > since)
    if status_filter:
        statement = statement.where(Digest.status == status_filter)
    if period:
        statement = statement.where(Digest.period == period)

    statement = (
        statement
        .order_by(Digest.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement).all())


@router.get("/new", response_model=NewDigestsResponse, dependencies=[Depends(verify_api_key)])
async def get_new_digests(
    session: Session = Depends(get_session),
    last_known_id: UUID | None = Query(default=None, description="ID of the last digest the client knows about"),
    since: datetime | None = Query(default=None, description="Return digests created after this datetime (UTC)"),
) -> NewDigestsResponse:
    """
    Check for new completed digests.

    Returns digests that are newer than the client's last known digest.
    Use either last_known_id OR since parameter to specify the cutoff.

    This endpoint is optimized for clients polling for new digests.
    """
    statement = select(Digest).where(Digest.status == "completed")

    if last_known_id:
        # Get the creation time of the last known digest
        last_digest = session.get(Digest, last_known_id)
        if last_digest:
            statement = statement.where(Digest.created_at > last_digest.created_at)
    elif since:
        statement = statement.where(Digest.created_at > since)

    statement = statement.order_by(Digest.created_at.desc())
    digests = list(session.exec(statement).all())

    return NewDigestsResponse(
        has_new=len(digests) > 0,
        count=len(digests),
        digests=digests,
    )


@router.get("/latest", response_model=DigestRead, dependencies=[Depends(verify_api_key)])
async def get_latest_digest(
    session: Session = Depends(get_session),
) -> Digest:
    """
    Get the most recent completed digest.

    Returns 404 if no completed digests exist.
    """
    statement = (
        select(Digest)
        .where(Digest.status == "completed")
        .order_by(Digest.completed_at.desc())
        .limit(1)
    )
    digest = session.exec(statement).first()

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed digests found",
        )

    return digest


@router.get("/{digest_id}/status", response_model=DigestStatusResponse, dependencies=[Depends(verify_api_key)])
async def get_digest_status(
    digest_id: UUID,
    session: Session = Depends(get_session),
) -> DigestStatusResponse:
    """
    Get the status of a digest job.

    Useful for polling progress during generation.
    """
    digest = session.get(Digest, digest_id)

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found",
        )

    # Calculate ETA based on progress (rough estimate)
    eta = None
    if digest.status == "processing" and digest.articles_enriched > 0:
        # Estimate based on average time per article
        remaining = digest.total_articles - digest.articles_enriched
        avg_time = 5  # seconds per article (rough estimate)
        eta = remaining * avg_time

    return DigestStatusResponse(
        id=digest.id,
        status=digest.status,
        stage=digest.stage,
        progress=DigestProgress(
            total_feeds=digest.total_feeds,
            feeds_fetched=digest.feeds_fetched,
            total_articles=digest.total_articles,
            articles_enriched=digest.articles_enriched,
        ),
        started_at=digest.created_at,
        eta_seconds=eta,
    )


@router.get("/{filename}", dependencies=[Depends(verify_api_key)])
async def download_digest(
    filename: str,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> FileResponse:
    """
    Download a digest EPUB file.

    The filename should be the EPUB filename (e.g., 2024-10-24_morning.epub).
    This also records download activity for inactivity tracking.
    """
    # Validate filename to prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    if not filename.endswith(".epub"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only EPUB files can be downloaded",
        )

    file_path = os.path.join(settings.output_dir, filename)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest file not found",
        )

    # Record download activity and mark digest as downloaded
    from app.services import activity_tracker
    activity_tracker.record_download()

    # Mark the specific digest as downloaded
    digest = session.exec(select(Digest).where(Digest.filename == filename)).first()
    if digest and not digest.downloaded_at:
        digest.downloaded_at = datetime.utcnow()
        session.add(digest)
        session.commit()

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/epub+zip",
    )


@router.delete("/{filename}", dependencies=[Depends(verify_api_key)])
async def delete_digest(
    filename: str,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> dict:
    """
    Delete a digest EPUB file.

    This also removes the database record.
    """
    # Validate filename
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    # Find and delete database record
    statement = select(Digest).where(Digest.filename == filename)
    digest = session.exec(statement).first()

    if digest:
        session.delete(digest)
        session.commit()

    # Delete file
    file_path = os.path.join(settings.output_dir, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return {"status": "deleted", "filename": filename}

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found",
        )

    return {"status": "deleted", "filename": filename, "note": "File already removed"}
