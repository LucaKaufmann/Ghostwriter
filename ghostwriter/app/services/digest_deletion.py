"""Crash-retryable deletion of a digest and only its owned data."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import Lock, RLock
from unicodedata import normalize
from uuid import UUID
from weakref import WeakValueDictionary

from sqlmodel import Session, select

from app.core.database import engine
from app.models.article_feedback import ArticleFeedback
from app.models.digest import Digest, DigestArticle
from app.models.media_item import MediaItem
from app.models.podcast_episode import PodcastEpisode
from app.models.schedule import Schedule


class DeletionConflict(Exception):
    pass


class DigestMissing(Exception):
    pass


_locks: WeakValueDictionary[UUID, RLock] = WeakValueDictionary()
_locks_guard = Lock()


def digest_lock(digest_id: UUID) -> RLock:
    with _locks_guard:
        return _locks.setdefault(digest_id, RLock())


@contextmanager
def immediate_session():
    """Acquire the SQLite writer slot before reading mutable eligibility."""
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            with Session(bind=connection) as session:
                yield session
                session.flush()
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def pdf_filename(epub: str) -> str:
    return f"{epub.rsplit('.', 1)[0]}.pdf" if "." in epub else f"{epub}.pdf"


def safe_digest_paths(output_dir: str | Path, filename: str) -> tuple[Path, Path]:
    if (
        not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or ".." in filename
        or not filename.lower().endswith(".epub")
        or filename.startswith(".")
    ):
        raise DeletionConflict("Unsafe digest filename")
    base = Path(output_dir).resolve()
    epub = base / filename
    pdf = base / pdf_filename(filename)
    if epub == pdf or epub.is_symlink() or pdf.is_symlink():
        raise DeletionConflict("Unsafe digest file path")
    if epub.parent != base or pdf.parent != base:
        raise DeletionConflict("Digest file escapes output directory")
    return epub, pdf


def _uuid_values(values: list[str] | None) -> set[UUID]:
    result = set()
    for value in values or []:
        try:
            result.add(UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            continue
    return result


def _check_references(session: Session, digest_id: UUID) -> None:
    article_ids = set(
        session.exec(
            select(DigestArticle.id).where(DigestArticle.digest_id == digest_id)
        ).all()
    )
    for episode in session.exec(select(PodcastEpisode)).all():
        if digest_id in _uuid_values(episode.digest_ids) or article_ids.intersection(
            _uuid_values(episode.article_ids)
        ):
            raise DeletionConflict("Digest is referenced by a podcast episode")


def check_owned_files(
    session: Session, digest: Digest, output_dir: str | Path
) -> tuple[Path, ...]:
    if not digest.filename:
        return ()
    paths = safe_digest_paths(output_dir, digest.filename)
    base = Path(output_dir).resolve()
    def claim_key(path: Path) -> str:
        # macOS volumes may resolve case/Unicode variants to the same file.
        return normalize("NFC", path.name).casefold()

    own_claims = {claim_key(path) for path in paths}
    for other in session.exec(select(Digest).where(Digest.id != digest.id)).all():
        if not other.filename or Path(other.filename).name != other.filename:
            continue
        # Even an invalid historical filename can claim the exact PDF path.
        other_paths = {base / other.filename, base / pdf_filename(other.filename)}
        if own_claims.intersection(claim_key(path) for path in other_paths) or any(
            path.exists() and other_path.exists() and path.samefile(other_path)
            for path in paths for other_path in other_paths
        ):
            raise DeletionConflict("Digest filename is shared")
    return paths


def _unlink(path: Path, output_dir: str | Path, filename: str) -> None:
    safe_digest_paths(output_dir, filename)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def delete_digest(digest_id: UUID, output_dir: str | Path) -> None:
    """Mark, unlink exact files, then remove children and parent atomically."""
    with digest_lock(digest_id):
        with immediate_session() as session:
            digest = session.get(Digest, digest_id)
            if digest is None:
                raise DigestMissing()
            _check_references(session, digest_id)
            paths = check_owned_files(session, digest, output_dir)
            if digest.status not in {"completed", "failed", "deleting"}:
                raise DeletionConflict("Digest is still being generated")
            digest.status = "deleting"
            session.add(digest)
            filename = digest.filename

        for path in paths:
            with immediate_session() as session:
                current = session.get(Digest, digest_id)
                if current is None or current.status != "deleting":
                    raise DeletionConflict("Digest deletion state changed")
                check_owned_files(session, current, output_dir)
                _unlink(path, output_dir, filename)

        with immediate_session() as session:
            digest = session.get(Digest, digest_id)
            if digest is None:
                raise DigestMissing()
            _check_references(session, digest_id)
            check_owned_files(session, digest, output_dir)
            if digest.status != "deleting":
                raise DeletionConflict("Digest deletion state changed")
            article_ids = set(
                session.exec(
                    select(DigestArticle.id).where(DigestArticle.digest_id == digest_id)
                ).all()
            )
            for feedback in session.exec(select(ArticleFeedback)).all():
                if (
                    feedback.digest_id == digest_id
                    or feedback.article_id in article_ids
                ):
                    session.delete(feedback)
            for media in session.exec(
                select(MediaItem).where(MediaItem.consumed_digest_id == digest_id)
            ).all():
                media.consumed_digest_id = None
                session.add(media)
            for schedule in session.exec(
                select(Schedule).where(Schedule.last_run_digest_id == digest_id)
            ).all():
                schedule.last_run_digest_id = None
                session.add(schedule)
            for article in session.exec(
                select(DigestArticle).where(DigestArticle.digest_id == digest_id)
            ).all():
                session.delete(article)
            session.delete(digest)
