"""Gmail newsletter integration service."""

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import time

import httpx
from lxml import html as lxml_html
from lxml.html import tostring as html_tostring

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

    def _generate_pkce_pair(self) -> tuple[str, str]:
        """Generate (code_verifier, code_challenge) for PKCE."""
        # RFC 7636: code_verifier length 43-128 characters
        verifier = secrets.token_urlsafe(64)[:128]
        challenge = hashlib.sha256(verifier.encode("utf-8")).digest()
        challenge_b64 = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode("utf-8")
        return verifier, challenge_b64

    def get_auth_url(self, redirect_uri: str) -> str:
        """Build Google OAuth consent URL and store redirect_uri for callback."""
        code_verifier, code_challenge = self._generate_pkce_pair()
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": self.settings.gmail_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GMAIL_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        # Store redirect_uri for use in callback
        os.makedirs(os.path.dirname(self._pending_oauth_path), exist_ok=True)
        with open(self._pending_oauth_path, "w") as f:
            json.dump(
                {
                    "redirect_uri": redirect_uri,
                    "state": state,
                    "code_verifier": code_verifier,
                    "created_at": int(time.time()),
                },
                f,
            )

        return str(httpx.URL(GOOGLE_AUTH_URL, params=params))

    async def exchange_code_with_callback(self, code: str, state: str | None) -> None:
        """Exchange authorization code using the stored redirect_uri from get_auth_url."""
        if not os.path.exists(self._pending_oauth_path):
            raise ValueError("No pending OAuth flow found. Start with get_auth_url first.")

        with open(self._pending_oauth_path) as f:
            pending = json.load(f)

        redirect_uri = pending.get("redirect_uri")
        pending_state = pending.get("state")
        code_verifier = pending.get("code_verifier")
        created_at = pending.get("created_at", 0)

        if not pending_state or not code_verifier:
            raise ValueError("OAuth state or PKCE verifier missing from pending state")
        if not state or state != pending_state:
            raise ValueError("OAuth state mismatch")
        if int(time.time()) - int(created_at) > 600:
            raise ValueError("OAuth state expired. Please retry.")
        if not redirect_uri:
            raise ValueError("No redirect_uri in pending OAuth state")

        await self.exchange_code(code, redirect_uri, code_verifier)

        # Clean up pending state
        try:
            os.remove(self._pending_oauth_path)
        except OSError:
            pass

    async def exchange_code(self, code: str, redirect_uri: str, code_verifier: str | None = None) -> None:
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
                    **({"code_verifier": code_verifier} if code_verifier else {}),
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

    async def fetch_newsletters(self) -> tuple[list[ExtractedArticle], list[str]]:
        """Fetch unread emails with the configured Gmail label.

        Returns a tuple of (articles, message_ids) from a single query,
        ensuring both lists are always in sync.
        """
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
                return [], []

            # List unread messages with this label (single query)
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
                logger.info("No newsletter emails found")
                return [], []

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
        return articles, message_ids

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

    # Tags whose content we want to keep (semantic / readable)
    _KEEP_TAGS = frozenset({
        "p", "h1", "h2", "h3", "h4", "h5", "h6",
        "a", "strong", "b", "em", "i", "u",
        "ul", "ol", "li",
        "blockquote", "pre", "code",
        "br", "hr",
        "figure", "figcaption",
        "sup", "sub", "span",
    })

    # Tags to remove entirely, including their content
    _STRIP_WITH_CONTENT = frozenset({
        "script", "style", "noscript", "iframe", "object", "embed",
        "form", "input", "button", "select", "textarea",
        "nav", "footer", "header",
    })

    # Attributes to keep on allowed tags
    _KEEP_ATTRS = frozenset({"href"})

    # Tracking image domains
    _TRACKING_DOMAINS = [
        "open.substack.com", "tracking.", "pixel.", "beacon.",
        "clicks.", "email.mg.", "list-manage.com/track",
    ]

    # Footer / unsubscribe text patterns
    _FOOTER_RE = re.compile(
        r"unsubscribe|manage\s+preferences|email\s+preferences|opt[\s-]?out|"
        r"view\s+in\s+browser|view\s+online|update\s+your\s+preferences",
        re.IGNORECASE,
    )

    def _clean_newsletter_html(self, raw_html: str) -> str:
        """Clean newsletter HTML for e-ink EPUB reading.

        Uses lxml for proper DOM-based cleaning:
        - Removes all images (newsletters are heavy with decorative/tracking images)
        - Flattens table-based layouts to plain content
        - Strips non-semantic tags while keeping their text
        - Removes empty elements and spacer elements
        - Removes footer/unsubscribe sections
        - Strips all attributes except href on links
        """
        try:
            doc = lxml_html.fromstring(raw_html)
        except Exception:
            # Fallback: return plain text if HTML parsing fails
            return re.sub(r"<[^>]+>", "", raw_html)

        # 1. Remove tags that should be deleted with all their content
        for tag in self._STRIP_WITH_CONTENT:
            for el in doc.xpath(f".//{tag}"):
                el.getparent().remove(el)

        # 2. Remove all images (decorative, tracking, etc.)
        for img in doc.xpath(".//img"):
            img.getparent().remove(img)

        # 3. Remove SVGs
        for svg in doc.xpath(".//*[local-name()='svg']"):
            svg.getparent().remove(svg)

        # 4. Remove footer/unsubscribe sections
        for el in doc.iter():
            text_content = el.text_content().strip()
            # Remove small blocks that look like footers
            if text_content and len(text_content) < 500 and self._FOOTER_RE.search(text_content):
                # Only remove if it's a block-level container
                if el.tag in ("div", "p", "td", "tr", "table", "section", "footer"):
                    parent = el.getparent()
                    if parent is not None:
                        parent.remove(el)

        # 5. Flatten tables to divs (tables in newsletters are almost always layout)
        for table in doc.xpath(".//table"):
            self._flatten_table(table)

        # 6. Unwrap non-semantic tags (keep text, drop the tag)
        # Process bottom-up to handle nesting
        for el in reversed(list(doc.iter())):
            if el.tag not in self._KEEP_TAGS and el.tag not in ("html", "body", "div"):
                el.drop_tag()

        # 7. Collapse nested divs into paragraphs where sensible
        self._collapse_divs(doc)

        # 8. Strip all attributes except href
        for el in doc.iter():
            attrs_to_remove = [a for a in el.attrib if a not in self._KEEP_ATTRS]
            for attr in attrs_to_remove:
                del el.attrib[attr]

        # 9. Remove empty elements
        self._remove_empty(doc)

        # 10. Serialize the body content
        body = doc.xpath(".//body")
        if body:
            content_el = body[0]
        else:
            content_el = doc

        parts = []
        if content_el.text and content_el.text.strip():
            parts.append(content_el.text.strip())
        for child in content_el:
            serialized = html_tostring(child, encoding="unicode", method="html")
            if serialized.strip():
                parts.append(serialized.strip())

        return "\n".join(parts)

    @staticmethod
    def _flatten_table(table):
        """Replace a table with its cell contents as divs."""
        parent = table.getparent()
        if parent is None:
            return

        idx = list(parent).index(table)
        # Collect text content from cells
        cells = table.xpath(".//td|.//th")
        new_elements = []
        for cell in cells:
            text = cell.text_content().strip()
            if text:
                div = lxml_html.Element("div")
                # Preserve child elements (links, etc.) not just text
                if len(cell) > 0:
                    div.text = cell.text
                    for child in cell:
                        div.append(child)
                else:
                    div.text = text
                new_elements.append(div)

        # Replace table with extracted content
        for i, el in enumerate(new_elements):
            parent.insert(idx + i, el)
        parent.remove(table)

    @staticmethod
    def _collapse_divs(doc):
        """Turn leaf-level divs (containing only text/inline) into paragraphs."""
        for div in doc.xpath(".//div"):
            # If div has no block-level children, convert to <p>
            has_block = any(
                child.tag in ("div", "p", "ul", "ol", "blockquote", "h1", "h2",
                              "h3", "h4", "h5", "h6", "pre", "hr", "table")
                for child in div
            )
            if not has_block and div.text_content().strip():
                div.tag = "p"

    @staticmethod
    def _remove_empty(doc):
        """Remove elements that have no text content and no meaningful children."""
        changed = True
        while changed:
            changed = False
            for el in doc.iter():
                if el.tag in ("br", "hr", "html", "body"):
                    continue
                if not el.text_content().strip() and len(el) == 0:
                    parent = el.getparent()
                    if parent is not None:
                        parent.remove(el)
                        changed = True
