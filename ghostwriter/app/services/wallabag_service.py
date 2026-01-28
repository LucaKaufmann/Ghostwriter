"""Wallabag integration service for fetching saved articles."""

import logging
import time

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class WallabagService:
    """
    Fetches unread articles from a Wallabag instance and marks them as processed.

    Uses OAuth2 password grant for authentication.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._token: str | None = None
        self._token_expires_at: float = 0

    @property
    def is_configured(self) -> bool:
        """Check if Wallabag credentials are fully configured."""
        s = self.settings
        return bool(
            s.wallabag_url
            and s.wallabag_client_id
            and s.wallabag_client_secret
            and s.wallabag_username
            and s.wallabag_password
        )

    async def _ensure_token(self) -> str:
        """Obtain or refresh the OAuth2 access token."""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        s = self.settings
        url = f"{s.wallabag_url.rstrip('/')}/oauth/v2/token"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                data={
                    "grant_type": "password",
                    "client_id": s.wallabag_client_id,
                    "client_secret": s.wallabag_client_secret,
                    "username": s.wallabag_username,
                    "password": s.wallabag_password,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)
        logger.info("Wallabag OAuth token acquired")
        return self._token

    async def fetch_unread_articles(self, max_articles: int | None = None) -> list[dict]:
        """
        Fetch unread (unarchived) articles from Wallabag.

        Returns a list of dicts with keys: id, title, url, content, domain_name.
        """
        if max_articles is None:
            max_articles = self.settings.wallabag_max_articles

        token = await self._ensure_token()
        base = self.settings.wallabag_url.rstrip("/")
        headers = {"Authorization": f"Bearer {token}"}

        articles: list[dict] = []
        page = 1
        per_page = min(max_articles, 30)

        async with httpx.AsyncClient(timeout=30) as client:
            while len(articles) < max_articles:
                resp = await client.get(
                    f"{base}/api/entries.json",
                    headers=headers,
                    params={
                        "archive": 0,
                        "sort": "created",
                        "order": "desc",
                        "page": page,
                        "perPage": per_page,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                items = data.get("_embedded", {}).get("items", [])
                if not items:
                    break

                for item in items:
                    if len(articles) >= max_articles:
                        break
                    articles.append({
                        "id": item["id"],
                        "title": item.get("title", "Untitled"),
                        "url": item.get("url", ""),
                        "content": item.get("content", ""),
                        "domain_name": item.get("domain_name"),
                    })

                total_pages = data.get("pages", 1)
                if page >= total_pages:
                    break
                page += 1

        logger.info(f"Fetched {len(articles)} unread Wallabag articles")
        return articles

    async def mark_processed(self, entry_id: int) -> None:
        """Archive the entry and add the configured tag."""
        token = await self._ensure_token()
        base = self.settings.wallabag_url.rstrip("/")
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=30) as client:
            # Archive the entry
            await client.patch(
                f"{base}/api/entries/{entry_id}.json",
                headers=headers,
                json={"archive": 1},
            )

            # Add tag
            tag = self.settings.wallabag_tag_on_process
            if tag:
                await client.post(
                    f"{base}/api/entries/{entry_id}/tags.json",
                    headers=headers,
                    json={"tags": tag},
                )

        logger.debug(f"Marked Wallabag entry {entry_id} as processed")
