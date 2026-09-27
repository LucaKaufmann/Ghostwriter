"""Versioned feed writes and replay-safe native mutation processing."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.feed import Feed
from app.models.feed_sync import FeedMutationReceipt, FeedSyncClock
from app.services.outbound_fetch import validate_public_url_bounded

MAX_VERSION = 2**53 - 1
SYNC_FIELDS = frozenset({"title", "is_active", "mode", "max_articles"})


def _begin_write(session: Session) -> None:
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _clock(session: Session) -> FeedSyncClock:
    clock = session.get(FeedSyncClock, 1)
    if clock is None:
        clock = FeedSyncClock()
        session.add(clock)
        session.flush()
    return clock


def _next_version(clock: FeedSyncClock) -> int:
    if clock.version >= MAX_VERSION:
        raise HTTPException(409, detail={"code": "feed_clock_exhausted"})
    clock.version += 1
    return clock.version


def snapshot(feed: Feed | None) -> dict | None:
    if feed is None:
        return None
    data = {"kind": "tombstone" if feed.deleted_at else "feed",
            "id": str(feed.id), "url": feed.url, "version": feed.version}
    if feed.deleted_at is None:
        data.update(title=feed.title, is_active=feed.is_active,
                    mode=feed.mode, max_articles=feed.max_articles)
    return data


def server_changed() -> HTTPException:
    return HTTPException(409, detail={"code": "server_changed"})


def validate_version(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_VERSION


def validate_fields(fields: object, *, creating: bool) -> bool:
    if not isinstance(fields, dict) or not fields or not set(fields) <= SYNC_FIELDS:
        return False
    if creating and set(fields) != SYNC_FIELDS:
        return False
    return all(
        (key == "title" and isinstance(value, str))
        or (key == "is_active" and type(value) is bool)
        or (key == "mode" and value in ("raw", "summarize") and isinstance(value, str))
        or (key == "max_articles" and type(value) is int and value >= 0)
        for key, value in fields.items()
    )


def _apply(session: Session, clock: FeedSyncClock, feed: Feed | None,
           url: str, kind: str, fields: dict) -> Feed | None:
    if kind == "delete":
        if feed is None or feed.deleted_at is not None:
            return feed
        now = datetime.utcnow()
        feed.is_active = False
        feed.deleted_at = now
        feed.updated_at = now
    else:
        if feed is None:
            feed = Feed(url=url, **fields)
            session.add(feed)
        else:
            changed = feed.deleted_at is not None
            for key, value in fields.items():
                if getattr(feed, key) != value:
                    setattr(feed, key, value)
                    changed = True
            if not changed:
                return feed
            feed.deleted_at = None
            feed.updated_at = datetime.utcnow()
    feed.version = _next_version(clock)
    session.add(feed)
    session.flush()
    return feed


def write_web(session: Session, *, url: str, kind: str, fields: dict,
              expected: int | None, feed_id: UUID | None = None) -> Feed:
    """CAS all first-party writes; expected=None permits only new creation."""
    _begin_write(session)
    try:
        clock = _clock(session)
        feed = session.exec(select(Feed).where(Feed.url == url)).first()
        if feed_id is not None and (feed is None or feed.id != feed_id):
            raise HTTPException(404, detail="Feed not found")
        if url.startswith("synthetic://"):
            raise HTTPException(422, detail="Synthetic feeds are internal")
        if feed is None:
            if kind != "upsert":
                raise HTTPException(404, detail="Feed not found")
            if expected is not None:
                raise HTTPException(409, detail={"code": "feed_conflict"})
        else:
            if expected is None:
                raise HTTPException(428, detail={"code": "feed_version_required", "current": snapshot(feed)})
            if feed.version != expected:
                raise HTTPException(409, detail={"code": "feed_conflict", "current": snapshot(feed)})
        result = _apply(session, clock, feed, url, kind, fields)
        session.commit()
        assert result is not None
        return result
    except BaseException:
        session.rollback()
        raise


def _result(op_id: str, status: str, **extra: object) -> dict:
    return {"op_id": op_id, "status": status, **extra}


def _reject(op_id: str, code: str, message: str) -> dict:
    return _result(op_id, "rejected", code=code, message=message)


def _payload_hash(item: dict) -> str:
    return hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _valid_url_shape(url: object) -> bool:
    if not isinstance(url, str) or url.startswith("synthetic://"):
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme in ("http", "https") and parsed.hostname is not None
                and parsed.username is None and parsed.password is None)
    except ValueError:
        return False


async def mutate_one(session: Session, instance_id: str, item: dict) -> dict:
    """One transaction per item; terminal results and writes commit together."""
    op_id = str(UUID(item["op_id"]))
    payload_hash = _payload_hash(item)
    # A durable replay needs no DNS. Close this read transaction before any
    # network-dependent validation, then recheck under the write lock below.
    receipt = session.get(FeedMutationReceipt, op_id)
    prior = (receipt.payload_hash, receipt.result_json) if receipt else None
    url = item.get("url")
    url_valid = _valid_url_shape(url)
    known_url = bool(session.exec(select(Feed.id).where(Feed.url == url)).first()) if url_valid and prior is None else False
    session.rollback()
    if prior is not None:
        if prior[0] != payload_hash:
            return _reject(op_id, "op_id_reused", "Operation ID was used with a different payload")
        return json.loads(prior[1])
    kind = item.get("kind")
    base = item.get("base_version", "missing")
    needs_new_url_admission = url_valid and kind == "upsert" and base is None and not known_url
    if needs_new_url_admission:
        try:
            await validate_public_url_bounded(url)
        except ValueError:
            url_valid = False
        except TimeoutError:
            raise HTTPException(503, detail={"code": "feed_validation_timeout"}) from None
    _begin_write(session)
    try:
        clock = _clock(session)
        if clock.server_instance_id != instance_id:
            raise server_changed()
        receipt = session.get(FeedMutationReceipt, op_id)
        if receipt is not None:
            if receipt.payload_hash != payload_hash:
                result = _reject(op_id, "op_id_reused", "Operation ID was used with a different payload")
            else:
                result = json.loads(receipt.result_json)
            session.commit()
            return result
        fields = item.get("fields")
        if not url_valid:
            result = _reject(op_id, "invalid_url", "A public HTTP(S) feed URL is required")
        else:
            result = None
        expected_keys = {"op_id", "url", "kind", "base_version"}
        if kind == "upsert":
            expected_keys.add("fields")
        if result is None and (set(item) != expected_keys or kind not in ("upsert", "delete") or
                               (base is not None and not validate_version(base)) or
                               base == "missing" or
                               (kind == "delete" and "fields" in item)):
            result = _reject(op_id, "invalid_fields", "Invalid mutation fields")
        feed = session.exec(select(Feed).where(Feed.url == url)).first() if result is None else None
        if result is None and kind == "upsert" and not validate_fields(fields, creating=feed is None):
            result = _reject(op_id, "invalid_fields", "Invalid feed fields")
        if result is None:
            if feed is None and base is not None:
                result = _reject(op_id, "unknown_base", "No feed exists at this base version")
            elif feed is not None and (base is None or feed.version != base):
                result = _result(op_id, "conflict", current=snapshot(feed))
            elif kind == "upsert" and feed is None and not needs_new_url_admission:
                # A row disappeared between preflight and CAS. Do not create
                # an unvalidated URL or write a terminal receipt.
                raise HTTPException(503, detail={"code": "feed_preflight_changed"})
            else:
                current = _apply(session, clock, feed, url, kind, fields or {})
                result = _result(op_id, "applied", current=snapshot(current))
        session.add(FeedMutationReceipt(op_id=op_id, payload_hash=payload_hash,
                                        result_json=json.dumps(result, separators=(",", ":"))))
        session.commit()
        return result
    except BaseException:
        session.rollback()
        raise


def rotate_identity(session: Session) -> str:
    _begin_write(session)
    try:
        clock = _clock(session)
        clock.server_instance_id = str(uuid4())
        session.add(clock)
        session.commit()
        return clock.server_instance_id
    except BaseException:
        session.rollback()
        raise
