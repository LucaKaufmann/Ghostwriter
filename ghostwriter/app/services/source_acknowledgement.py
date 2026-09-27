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


async def drain_pending(
    *, engine=default_engine, limit: int = 50, deadline_seconds: float = 30,
    newsletter_factory: Callable[[], NewsletterService] | None = None,
    wallabag_factory: Callable[[Session], WallabagService] | None = None,
) -> None:
    """Try a bounded batch; any uncertain remote outcome remains retryable."""
    if _drain_lock.locked():
        return
    newsletter_factory = newsletter_factory or (lambda: NewsletterService(get_settings()))
    wallabag_factory = wallabag_factory or (
        lambda session: WallabagService.from_db_or_settings(session, get_settings())
    )
    async with _drain_lock:
        deadline = asyncio.get_running_loop().time() + deadline_seconds
        with Session(engine) as session:
            ids = session.exec(
                select(SourceAcknowledgement.id)
                .where(SourceAcknowledgement.state.in_(["pending", "suspended"]))
                .order_by(
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
