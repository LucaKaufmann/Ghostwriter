"""Gmail newsletter integration service."""

import base64
import json
import logging
import os
import re

import httpx

from app.core.config import Settings, get_settings
from app.services.content_processor import ContentProcessor, ExtractedArticle

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_SCOPES = "https://www.googleapis.com/auth/gmail.modify"


class NewsletterService:
    """
    Fetches newsletter emails from Gmail via OAuth2 and REST API.

    Requires a Gmail label (default: "Ghostwriter") to identify newsletter emails.
    Uses OAuth2 authorization code flow for authentication.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._token_path = os.path.join(self.settings.data_dir, "gmail_token.json")
        self._pending_oauth_path = os.path.join(self.settings.data_dir, "gmail_oauth_pending.json")

    @property
    def is_configured(self) -> bool:
        """Check if Gmail OAuth is fully configured (credentials + token)."""
        return bool(
            self.settings.gmail_client_id
            and self.settings.gmail_client_secret
            and os.path.exists(self._token_path)
        )

    @property
    def is_oauth_ready(self) -> bool:
        """Check if client credentials are present but token is missing."""
        return bool(
            self.settings.gmail_client_id
            and self.settings.gmail_client_secret
            and not os.path.exists(self._token_path)
        )

    def get_auth_url(self, redirect_uri: str) -> str:
        """Build Google OAuth consent URL and store redirect_uri for callback."""
        params = {
            "client_id": self.settings.gmail_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GMAIL_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
        }
        # Store redirect_uri for use in callback
        os.makedirs(os.path.dirname(self._pending_oauth_path), exist_ok=True)
        with open(self._pending_oauth_path, "w") as f:
            json.dump({"redirect_uri": redirect_uri}, f)

        return str(httpx.URL(GOOGLE_AUTH_URL, params=params))

    async def exchange_code_with_callback(self, code: str) -> None:
        """Exchange authorization code using the stored redirect_uri from get_auth_url."""
        if not os.path.exists(self._pending_oauth_path):
            raise ValueError("No pending OAuth flow found. Start with get_auth_url first.")

        with open(self._pending_oauth_path) as f:
            pending = json.load(f)

        redirect_uri = pending.get("redirect_uri")
        if not redirect_uri:
            raise ValueError("No redirect_uri in pending OAuth state")

        await self.exchange_code(code, redirect_uri)

        # Clean up pending state
        try:
            os.remove(self._pending_oauth_path)
        except OSError:
            pass

    async def exchange_code(self, code: str, redirect_uri: str) -> None:
        """Exchange authorization code for tokens and save to disk."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.settings.gmail_client_id,
                    "client_secret": self.settings.gmail_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        os.makedirs(os.path.dirname(self._token_path), exist_ok=True)
        with open(self._token_path, "w") as f:
            json.dump(token_data, f)
        logger.info("Gmail OAuth token saved")

    async def _get_access_token(self) -> str:
        """Load token from disk, refreshing if needed."""
        with open(self._token_path) as f:
            token_data = json.load(f)

        # Try refreshing if we have a refresh token
        if "refresh_token" in token_data:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    GOOGLE_TOKEN_URL,
                    data={
                        "client_id": self.settings.gmail_client_id,
                        "client_secret": self.settings.gmail_client_secret,
                        "refresh_token": token_data["refresh_token"],
                        "grant_type": "refresh_token",
                    },
                )
                if resp.status_code == 200:
                    new_data = resp.json()
                    # Preserve refresh_token (not always returned on refresh)
                    new_data.setdefault("refresh_token", token_data["refresh_token"])
                    with open(self._token_path, "w") as f:
                        json.dump(new_data, f)
                    return new_data["access_token"]

        return token_data["access_token"]

    async def fetch_newsletters(self) -> list[ExtractedArticle]:
        """Fetch unread emails with the configured Gmail label."""
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        label = self.settings.gmail_label
        max_results = self.settings.gmail_max_articles

        articles: list[ExtractedArticle] = []
        message_ids: list[str] = []

        async with httpx.AsyncClient(timeout=30) as client:
            # Find the label ID
            resp = await client.get(f"{GMAIL_API_BASE}/labels", headers=headers)
            resp.raise_for_status()
            label_id = None
            for lbl in resp.json().get("labels", []):
                if lbl["name"].lower() == label.lower():
                    label_id = lbl["id"]
                    break

            if not label_id:
                logger.warning(f"Gmail label '{label}' not found")
                return []

            # List unread messages with this label
            resp = await client.get(
                f"{GMAIL_API_BASE}/messages",
                headers=headers,
                params={
                    "labelIds": label_id,
                    "q": "is:unread",
                    "maxResults": max_results,
                },
            )
            resp.raise_for_status()
            messages = resp.json().get("messages", [])

            if not messages:
                logger.info("No unread newsletter emails found")
                return []

            # Fetch each message
            for msg_ref in messages:
                msg_id = msg_ref["id"]
                resp = await client.get(
                    f"{GMAIL_API_BASE}/messages/{msg_id}",
                    headers=headers,
                    params={"format": "full"},
                )
                resp.raise_for_status()
                msg_data = resp.json()

                article = self._parse_email(msg_data)
                if article:
                    articles.append(article)
                    message_ids.append(msg_id)

        logger.info(f"Fetched {len(articles)} newsletter emails")
        return articles

    async def get_fetched_message_ids(self) -> list[str]:
        """Get message IDs from the most recent fetch (for mark_processed)."""
        # Re-fetch to get IDs - this is called after fetch_newsletters
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        label = self.settings.gmail_label

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{GMAIL_API_BASE}/labels", headers=headers)
            resp.raise_for_status()
            label_id = None
            for lbl in resp.json().get("labels", []):
                if lbl["name"].lower() == label.lower():
                    label_id = lbl["id"]
                    break
            if not label_id:
                return []

            resp = await client.get(
                f"{GMAIL_API_BASE}/messages",
                headers=headers,
                params={
                    "labelIds": label_id,
                    "q": "is:unread",
                    "maxResults": self.settings.gmail_max_articles,
                },
            )
            resp.raise_for_status()
            return [m["id"] for m in resp.json().get("messages", [])]

    async def mark_processed(self, message_ids: list[str]) -> None:
        """Mark emails as read by removing UNREAD label."""
        if not message_ids:
            return
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=30) as client:
            # Batch modify
            resp = await client.post(
                f"{GMAIL_API_BASE}/messages/batchModify",
                headers=headers,
                json={
                    "ids": message_ids,
                    "removeLabelIds": ["UNREAD"],
                },
            )
            resp.raise_for_status()
        logger.info(f"Marked {len(message_ids)} newsletter emails as read")

    def _parse_email(self, msg: dict) -> ExtractedArticle | None:
        """Extract article data from a Gmail message."""
        headers_list = msg.get("payload", {}).get("headers", [])
        headers_map = {h["name"].lower(): h["value"] for h in headers_list}

        subject = headers_map.get("subject", "Untitled Newsletter")
        sender = headers_map.get("from", "")

        html_body = self._extract_html_body(msg.get("payload", {}))
        if not html_body:
            logger.debug(f"No HTML body for email: {subject}")
            return None

        cleaned = self._clean_newsletter_html(html_body)
        # Strip tags for plain text content
        plain = re.sub(r"<[^>]+>", "", cleaned)
        plain = re.sub(r"\s+", " ", plain).strip()

        if not plain:
            return None

        word_count = ContentProcessor.count_words(plain)
        msg_id = msg.get("id", "")

        return ExtractedArticle(
            guid=f"gmail-{msg_id}",
            url=f"https://mail.google.com/mail/u/0/#inbox/{msg_id}",
            title=subject,
            content=cleaned,
            author=sender,
            word_count=word_count,
            is_summary=False,
            ai_failed=False,
            processing_ms=0,
        )

    def _extract_html_body(self, payload: dict) -> str | None:
        """Recursively walk MIME parts to find text/html."""
        mime_type = payload.get("mimeType", "")

        if mime_type == "text/html":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        # Walk multipart
        for part in payload.get("parts", []):
            result = self._extract_html_body(part)
            if result:
                return result

        return None

    def _clean_newsletter_html(self, html: str) -> str:
        """Strip tracking pixels, scripts, styles, and other noise from newsletter HTML."""
        # Remove <script> and <style> tags with content
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove tracking pixels (1x1 images)
        html = re.sub(
            r'<img[^>]*(?:width\s*=\s*["\']?1["\']?[^>]*height\s*=\s*["\']?1["\']?|'
            r'height\s*=\s*["\']?1["\']?[^>]*width\s*=\s*["\']?1["\']?)[^>]*/?>',
            "", html, flags=re.IGNORECASE,
        )

        # Remove common tracking image patterns
        tracking_domains = [
            "open.substack.com", "tracking.", "pixel.", "beacon.",
            "clicks.", "email.mg.", "list-manage.com/track",
        ]
        for domain in tracking_domains:
            html = re.sub(
                rf'<img[^>]*src\s*=\s*["\'][^"\']*{re.escape(domain)}[^"\']*["\'][^>]*/?>',
                "", html, flags=re.IGNORECASE,
            )

        # Remove inline style attributes
        html = re.sub(r'\s+style\s*=\s*"[^"]*"', "", html, flags=re.IGNORECASE)
        html = re.sub(r"\s+style\s*=\s*'[^']*'", "", html, flags=re.IGNORECASE)

        # Remove bgcolor attributes
        html = re.sub(r'\s+bgcolor\s*=\s*"[^"]*"', "", html, flags=re.IGNORECASE)

        # Remove unsubscribe footers (common patterns)
        html = re.sub(
            r'<[^>]*class\s*=\s*["\'][^"\']*unsubscribe[^"\']*["\'][^>]*>.*?</[^>]+>',
            "", html, flags=re.DOTALL | re.IGNORECASE,
        )

        return html
