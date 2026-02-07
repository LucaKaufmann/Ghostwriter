"""Push notification delivery for completed digests."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from jose import jwt
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.database import engine
from app.models.digest import Digest
from app.models.push_device import PushDevice

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _SendResult:
    device_db_id: UUID
    ok: bool
    invalid_token: bool = False
    error: str | None = None


class PushNotificationService:
    """Sends push notifications to registered devices."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        self._apns_jwt: str | None = None
        self._apns_jwt_iat: int = 0

        self._fcm_access_token: str | None = None
        self._fcm_access_token_exp: float = 0.0
        self._fcm_sa: dict[str, Any] | None = None
        self._fcm_token_lock = asyncio.Lock()

    # ===== Public API =====

    async def notify_digest_ready(self, digest_id: UUID) -> None:
        """
        Notify all enabled devices when a digest is completed.

        This is best-effort and should never raise to callers.
        """
        try:
            await self._notify_digest_ready_inner(digest_id)
        except Exception:
            logger.exception("Push notify failed", extra={"digest_id": str(digest_id)})

    # ===== Internal =====

    async def _notify_digest_ready_inner(self, digest_id: UUID) -> None:
        with Session(engine) as session:
            digest = session.get(Digest, digest_id)
            if not digest:
                return
            if digest.status != "completed":
                return
            if (digest.article_count or 0) <= 0:
                return

            devices = list(
                session.exec(
                    select(PushDevice).where(
                        PushDevice.enabled.is_(True),
                        PushDevice.disabled_at.is_(None),
                    )
                ).all()
            )

        if not devices:
            return

        title, body = self._digest_message(digest)
        payload_data = self._digest_payload_data(digest)

        tasks: list[asyncio.Task[_SendResult]] = []
        for device in devices:
            if device.platform == "ios" and self._apns_is_configured():
                tasks.append(
                    asyncio.create_task(
                        self._send_apns(device, title=title, body=body, data=payload_data)
                    )
                )
            elif device.platform == "android" and self._fcm_is_configured():
                tasks.append(
                    asyncio.create_task(
                        self._send_fcm(device, title=title, body=body, data=payload_data)
                    )
                )

        if not tasks:
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)
        normalized: list[_SendResult] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("Push send task raised", extra={"error": str(r)})
                continue
            normalized.append(r)

        if not normalized:
            return

        now = datetime.utcnow()
        with Session(engine) as session:
            for result in normalized:
                d = session.get(PushDevice, result.device_db_id)
                if not d:
                    continue
                d.updated_at = now
                if result.ok:
                    d.failure_count = 0
                    d.last_error = None
                else:
                    d.failure_count = (d.failure_count or 0) + 1
                    d.last_error = (result.error or "push send failed")[:500]
                    if result.invalid_token:
                        d.enabled = False
                        d.disabled_at = now
                session.add(d)
            session.commit()

    def _digest_message(self, digest: Digest) -> tuple[str, str]:
        title = "New digest available"
        period = (digest.period or "").strip().lower()
        if period in {"morning", "noon", "evening"}:
            body = f"{period.capitalize()} digest is ready."
        else:
            body = "Your digest is ready."
        return title, body

    def _digest_payload_data(self, digest: Digest) -> dict[str, str]:
        return {
            "event": "digest_ready",
            "digest_id": str(digest.id),
            "period": str(digest.period or ""),
            "article_count": str(digest.article_count or 0),
            "completed_at": digest.completed_at.isoformat() if digest.completed_at else "",
            "filename": str(digest.filename or ""),
        }

    # ===== APNs =====

    def _apns_is_configured(self) -> bool:
        return bool(
            self.settings.apns_team_id
            and self.settings.apns_key_id
            and self.settings.apns_private_key_path
            and self.settings.apns_bundle_id
        )

    def _get_apns_jwt(self) -> str:
        now = int(time.time())
        # Apple recommends reusing a token for up to 60 minutes.
        if self._apns_jwt and (now - self._apns_jwt_iat) < 50 * 60:
            return self._apns_jwt

        key_path = Path(self.settings.apns_private_key_path).expanduser()
        key = key_path.read_text(encoding="utf-8")
        token = jwt.encode(
            {"iss": self.settings.apns_team_id, "iat": now},
            key,
            algorithm="ES256",
            headers={"kid": self.settings.apns_key_id},
        )
        self._apns_jwt = token
        self._apns_jwt_iat = now
        return token

    async def _send_apns(
        self, device: PushDevice, *, title: str, body: str, data: dict[str, str]
    ) -> _SendResult:
        device_token = device.token.strip()
        if not device_token:
            return _SendResult(device_db_id=device.id, ok=False, error="missing APNs token")

        base = (
            "https://api.sandbox.push.apple.com"
            if self.settings.apns_use_sandbox
            else "https://api.push.apple.com"
        )
        url = f"{base}/3/device/{device_token}"

        payload = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
                "content-available": 1,
            },
            **data,
        }

        headers = {
            "authorization": f"bearer {self._get_apns_jwt()}",
            "apns-topic": self.settings.apns_bundle_id,
            "apns-push-type": "alert",
            "apns-priority": "10",
        }

        try:
            async with httpx.AsyncClient(http2=True, timeout=10) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except Exception as e:
            return _SendResult(device_db_id=device.id, ok=False, error=str(e))

        if resp.status_code == 200:
            return _SendResult(device_db_id=device.id, ok=True)

        reason = None
        try:
            reason = resp.json().get("reason")
        except Exception:
            reason = resp.text[:200]

        invalid = resp.status_code in {400, 410} and str(reason) in {
            "BadDeviceToken",
            "Unregistered",
            "DeviceTokenNotForTopic",
        }
        return _SendResult(
            device_db_id=device.id,
            ok=False,
            invalid_token=invalid,
            error=f"APNs {resp.status_code}: {reason}",
        )

    # ===== FCM =====

    def _fcm_is_configured(self) -> bool:
        return bool(self.settings.fcm_service_account_path)

    def _load_fcm_service_account(self) -> dict[str, Any]:
        if self._fcm_sa is not None:
            return self._fcm_sa

        path = Path(self.settings.fcm_service_account_path).expanduser()
        data = json.loads(path.read_text(encoding="utf-8"))
        self._fcm_sa = data
        return data

    async def _get_fcm_access_token(self) -> tuple[str, str]:
        """
        Get a cached OAuth2 access token for FCM HTTP v1.

        Returns (access_token, project_id).
        """
        async with self._fcm_token_lock:
            now = time.time()
            sa = self._load_fcm_service_account()
            project_id = self.settings.fcm_project_id or sa.get("project_id") or ""
            if not project_id:
                raise ValueError("FCM project_id missing (set FCM_PROJECT_ID or include in service account)")

            if self._fcm_access_token and now < (self._fcm_access_token_exp - 60):
                return self._fcm_access_token, project_id

            client_email = sa.get("client_email")
            private_key = sa.get("private_key")
            if not client_email or not private_key:
                raise ValueError("FCM service account missing client_email/private_key")

            iat = int(now)
            assertion = jwt.encode(
                {
                    "iss": client_email,
                    "sub": client_email,
                    "aud": "https://oauth2.googleapis.com/token",
                    "iat": iat,
                    "exp": iat + 3600,
                    "scope": "https://www.googleapis.com/auth/firebase.messaging",
                },
                private_key,
                algorithm="RS256",
            )

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": assertion,
                    },
                )
                resp.raise_for_status()
                token_data = resp.json()

            access_token = token_data["access_token"]
            expires_in = float(token_data.get("expires_in", 3600))
            self._fcm_access_token = access_token
            self._fcm_access_token_exp = now + expires_in
            return access_token, project_id

    async def _send_fcm(
        self, device: PushDevice, *, title: str, body: str, data: dict[str, str]
    ) -> _SendResult:
        token = device.token.strip()
        if not token:
            return _SendResult(device_db_id=device.id, ok=False, error="missing FCM token")

        try:
            access_token, project_id = await self._get_fcm_access_token()
        except Exception as e:
            return _SendResult(device_db_id=device.id, ok=False, error=str(e))

        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        headers = {"authorization": f"Bearer {access_token}"}
        data_with_text = {**data, "title": title, "body": body}
        body_json: dict[str, Any] = {
            "message": {
                "token": token,
                # Use data-only messages so the client can trigger background sync reliably.
                "data": data_with_text,
                "android": {"priority": "HIGH"},
            }
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, headers=headers, json=body_json)
        except Exception as e:
            return _SendResult(device_db_id=device.id, ok=False, error=str(e))

        if resp.status_code == 200:
            return _SendResult(device_db_id=device.id, ok=True)

        invalid = False
        reason = resp.text[:200]
        try:
            j = resp.json()
            error = j.get("error", {})
            status_str = str(error.get("status") or "")
            message = str(error.get("message") or "")
            reason = f"{status_str}: {message}".strip(": ")
            invalid = status_str == "NOT_FOUND" and "Requested entity was not found" in message
            invalid = invalid or status_str == "UNREGISTERED"
        except Exception:
            pass

        return _SendResult(
            device_db_id=device.id,
            ok=False,
            invalid_token=invalid,
            error=f"FCM {resp.status_code}: {reason}",
        )
