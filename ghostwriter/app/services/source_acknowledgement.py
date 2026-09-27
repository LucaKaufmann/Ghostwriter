"""At-least-once acknowledgement of source items in published digests."""

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import engine as default_engine
from app.models.client_config import ClientConfig
from app.models.source_acknowledgement import SourceAcknowledgement
from app.models.wallabag_config import WallabagConfig
from app.services.newsletter_service import NewsletterService
from app.services.wallabag_service import WallabagService

logger = logging.getLogger(__name__)
_drain_lock = asyncio.Lock()


def _fingerprint(*parts: str) -> str:
    # Domain separation and JSON encoding avoid ambiguous concatenations.
    value = json.dumps(["ghostwriter-source-ack-v1", *parts], separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def gmail_binding_for_account(account_id: str, service: NewsletterService) -> tuple[str, str]:
    account = account_id.strip().casefold()
    client = service.settings.gmail_client_id.strip()
    if not account or not client:
        raise ValueError("Gmail source identity unavailable")
    identity = _fingerprint("gmail", account, client)
    return identity, _fingerprint("gmail-action", identity, service.settings.gmail_label.casefold(), "mark_read")


def wallabag_binding(service: WallabagService) -> tuple[str, str]:
    settings = service.settings
    parts = urlsplit(settings.wallabag_url.strip())
    endpoint = urlunsplit((
        parts.scheme.casefold(), parts.netloc.casefold(),
        parts.path.rstrip("/"), parts.query, "",
    ))
    username = settings.wallabag_username.strip()
    client = settings.wallabag_client_id.strip()
    if not endpoint or not username or not client:
        raise ValueError("Wallabag source identity unavailable")
    identity = _fingerprint("wallabag", endpoint, username, client)
    return identity, _fingerprint(
        "wallabag-action", identity, settings.wallabag_tag_on_process, "archive_and_tag"
    )


def add_intent(
    session: Session, digest_id: UUID, provider: str, binding: tuple[str, str],
    external_item_id: str,
) -> None:
    action = "mark_read" if provider == "gmail" else "archive_and_tag"
    existing = session.exec(
        select(SourceAcknowledgement.id).where(
            SourceAcknowledgement.digest_id == digest_id,
            SourceAcknowledgement.provider == provider,
            SourceAcknowledgement.source_identity == binding[0],
            SourceAcknowledgement.source_config_fingerprint == binding[1],
            SourceAcknowledgement.external_item_id == external_item_id,
            SourceAcknowledgement.action == action,
        )
    ).first()
    if existing is None:
        session.add(SourceAcknowledgement(
            digest_id=digest_id, provider=provider,
            source_identity=binding[0], source_config_fingerprint=binding[1],
            external_item_id=external_item_id, action=action,
        ))


_pending_requests: dict[tuple[int, UUID | None], dict] = {}
_follow_up_tasks: set[asyncio.Task] = set()


def _pop_requested() -> dict | None:
    for key in _pending_requests:
        if key[1] is not None:  # Newly published editions get priority.
            return _pending_requests.pop(key)
    if _pending_requests:
        return _pending_requests.pop(next(iter(_pending_requests)))
    return None


def _schedule_follow_up(request: dict) -> None:
    task = asyncio.create_task(drain_pending(**request))
    _follow_up_tasks.add(task)

    def report_failure(completed: asyncio.Task) -> None:
        _follow_up_tasks.discard(completed)
        if not completed.cancelled() and completed.exception() is not None:
            logger.error(
                "Source acknowledgement follow-up failed: %s",
                type(completed.exception()).__name__,
            )

    task.add_done_callback(report_failure)


async def drain_pending(
    *, engine=default_engine, limit: int = 50, deadline_seconds: float = 30,
    newsletter_factory: Callable[[], NewsletterService] | None = None,
    wallabag_factory: Callable[[Session], WallabagService] | None = None,
    digest_id: UUID | None = None,
    request_follow_up: bool = True,
    unattempted_only: bool = False,
) -> None:
    """Drain one bounded pass; coalesce overlapping requests for later passes."""
    newsletter_factory = newsletter_factory or (lambda: NewsletterService(get_settings()))
    wallabag_factory = wallabag_factory or (
        lambda session: WallabagService.from_db_or_settings(session, get_settings())
    )
    request = {
        "engine": engine,
        "limit": limit,
        "deadline_seconds": deadline_seconds,
        "newsletter_factory": newsletter_factory,
        "wallabag_factory": wallabag_factory,
        "digest_id": digest_id,
        "unattempted_only": unattempted_only,
    }
    if _drain_lock.locked():
        if request_follow_up:
            _pending_requests[(id(engine), digest_id)] = request
        return
    async with _drain_lock:
        try:
            await _drain_once(**request)
        finally:
            # Run one requested follow-up in its own bounded pass after release.
            # This also preserves another caller's request if this pass cancels.
            follow_up = _pop_requested()
            if follow_up is not None:
                asyncio.get_running_loop().call_soon(_schedule_follow_up, follow_up)


async def _drain_once(
    *, engine, limit: int, deadline_seconds: float,
    newsletter_factory: Callable[[], NewsletterService],
    wallabag_factory: Callable[[Session], WallabagService],
    digest_id: UUID | None,
    unattempted_only: bool,
) -> None:
    deadline = asyncio.get_running_loop().time() + deadline_seconds
    attempted_count = 0
    with Session(engine) as session:
        statement = select(SourceAcknowledgement.id).where(
            SourceAcknowledgement.state.in_(["pending", "suspended"])
        )
        if digest_id is not None:
            statement = statement.where(SourceAcknowledgement.digest_id == digest_id)
        if unattempted_only:
            statement = statement.where(SourceAcknowledgement.last_attempt_at.is_(None))
        ids = session.exec(
            statement.order_by(
                SourceAcknowledgement.last_attempt_at,
                SourceAcknowledgement.created_at,
                SourceAcknowledgement.id,
            )
            .limit(limit)
        ).all()
    for receipt_id in ids:
        if asyncio.get_running_loop().time() >= deadline:
            break
        with Session(engine) as session:
            receipt = session.get(SourceAcknowledgement, receipt_id)
            if receipt is None or receipt.state == "done":
                continue
            attempted_count += 1
            provider = receipt.provider
            item_id = receipt.external_item_id
            expected = (receipt.source_identity, receipt.source_config_fingerprint)
            if provider == "gmail":
                config = session.exec(select(ClientConfig)).first()
                enabled = config.newsletters_enabled if config else True
                service = newsletter_factory() if enabled else None
            elif provider == "wallabag":
                config = session.exec(select(WallabagConfig)).first()
                enabled = config.enabled if config else True
                service = wallabag_factory(session) if enabled else None
            else:
                service = None
        token: str | None = None
        try:
            async with asyncio.timeout_at(deadline):
                if service is None or not service.is_configured:
                    raise ValueError("source_unavailable")
                if provider == "gmail":
                    token = await service._get_access_token()
                    account = await service.get_account_id_for_token(token)
                    actual = gmail_binding_for_account(account, service)
                else:
                    actual = wallabag_binding(service)
                if actual != expected:
                    raise ValueError("source_changed")
        except TimeoutError:
            _record_pending(engine, receipt_id, "deadline_exceeded")
            break
        except Exception as exc:
            # Identity errors never dispatch to a possibly different account.
            with Session(engine) as session:
                receipt = session.get(SourceAcknowledgement, receipt_id)
                if receipt and receipt.state != "done":
                    receipt.state = "suspended"
                    receipt.last_error_code = (
                        "source_changed"
                        if isinstance(exc, ValueError) and str(exc) == "source_changed"
                        else "identity_unavailable"
                    )
                    receipt.attempt_count += 1
                    receipt.last_attempt_at = datetime.utcnow()
                    session.add(receipt)
                    session.commit()
            continue
        try:
            async with asyncio.timeout_at(deadline):
                if provider == "gmail":
                    assert token is not None
                    await service.mark_processed_with_token([item_id], token)
                else:
                    await service.mark_processed(int(item_id))
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            _record_pending(engine, receipt_id, "deadline_exceeded")
            break
        except Exception as exc:
            _record_pending(engine, receipt_id, type(exc).__name__[:64])
            logger.warning("Source acknowledgement deferred: provider=%s", provider)
            continue
        with Session(engine) as session:
            receipt = session.get(SourceAcknowledgement, receipt_id)
            if receipt and receipt.state != "done":
                receipt.state = "done"
                receipt.attempt_count += 1
                receipt.last_attempt_at = datetime.utcnow()
                receipt.completed_at = datetime.utcnow()
                receipt.last_error_code = None
                session.add(receipt)
                session.commit()

    # A newly published edition may contain more items than one pass's limit.
    # Continue only for never-attempted items; failed items wait for a later
    # run/startup and cannot create a hot retry loop.
    if digest_id is not None and attempted_count:
        with Session(engine) as session:
            unattempted = session.exec(
                select(SourceAcknowledgement.id).where(
                    SourceAcknowledgement.digest_id == digest_id,
                    SourceAcknowledgement.state.in_(["pending", "suspended"]),
                    SourceAcknowledgement.last_attempt_at.is_(None),
                ).limit(1)
            ).first()
        if unattempted is not None:
            _pending_requests[(id(engine), digest_id)] = {
                "engine": engine,
                "limit": limit,
                "deadline_seconds": deadline_seconds,
                "newsletter_factory": newsletter_factory,
                "wallabag_factory": wallabag_factory,
                "digest_id": digest_id,
                "unattempted_only": True,
            }



def _record_pending(engine, receipt_id: UUID, code: str) -> None:
    with Session(engine) as session:
        receipt = session.get(SourceAcknowledgement, receipt_id)
        if receipt and receipt.state != "done":
            receipt.state = "pending"
            receipt.attempt_count += 1
            receipt.last_attempt_at = datetime.utcnow()
            receipt.last_error_code = code
            session.add(receipt)
            session.commit()
