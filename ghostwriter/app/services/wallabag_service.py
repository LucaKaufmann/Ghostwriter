"""Wallabag integration service for fetching saved articles."""

import logging
import time

import httpx
from sqlmodel import Session, select

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class _WallabagSettings:
    """Lightweight settings-like object for DB-backed Wallabag config."""

    def __init__(
        self,
        wallabag_url: str,
        wallabag_client_id: str,
        wallabag_client_secret: str,
        wallabag_username: str,
        wallabag_password: str,
        wallabag_mode: str,
        wallabag_max_articles: int,
        wallabag_tag_on_process: str,
    ):
        self.wallabag_url = wallabag_url
        self.wallabag_client_id = wallabag_client_id
        self.wallabag_client_secret = wallabag_client_secret
        self.wallabag_username = wallabag_username
        self.wallabag_password = wallabag_password
        self.wallabag_mode = wallabag_mode
        self.wallabag_max_articles = wallabag_max_articles
        self.wallabag_tag_on_process = wallabag_tag_on_process


class WallabagService:
    """
    Fetches unread articles from a Wallabag instance and marks them as processed.

    Uses OAuth2 password grant for authentication.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._token: str | None = None
        self._token_expires_at: float = 0

    @classmethod
    def from_db_or_settings(cls, session: Session, settings: Settings | None = None) -> "WallabagService":
        """Create a WallabagService preferring DB config, falling back to env vars."""
        from app.models.wallabag_config import WallabagConfig

        settings = settings or get_settings()
        db_config = session.exec(select(WallabagConfig)).first()

        if db_config and db_config.url:
            wrapper = _WallabagSettings(
                wallabag_url=db_config.url,
                wallabag_client_id=db_config.client_id,
                wallabag_client_secret=db_config.client_secret,
                wallabag_username=db_config.username,
                wallabag_password=db_config.password,
                wallabag_mode=db_config.mode,
                wallabag_max_articles=db_config.max_articles,
                wallabag_tag_on_process=db_config.tag_on_process,
            )
            svc = cls.__new__(cls)
            svc.settings = wrapper
            svc._token = None
            svc._token_expires_at = 0
            return svc

        return cls(settings)

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
        logger.info(f"Requesting Wallabag OAuth token from {url}")

        try:
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
                if resp.status_code != 200:
                    body = resp.text[:500]
                    logger.error(
                        f"Wallabag OAuth token request failed: "
                        f"HTTP {resp.status_code} - {body}"
                    )
                    resp.raise_for_status()
                data = resp.json()
        except httpx.ConnectError as e:
            logger.error(f"Wallabag connection failed (is the URL correct?): {url} - {e!r}")
            raise
        except httpx.TimeoutException as e:
            logger.error(f"Wallabag OAuth request timed out: {url} - {e!r}")
            raise

        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)
        logger.info("Wallabag OAuth token acquired successfully")
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

        logger.info(f"Fetching up to {max_articles} unread Wallabag articles from {base}")

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
                if resp.status_code != 200:
                    body = resp.text[:500]
                    logger.error(
                        f"Wallabag entries fetch failed: "
                        f"HTTP {resp.status_code} - {body}"
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
            resp = await client.patch(
                f"{base}/api/entries/{entry_id}.json",
                headers=headers,
                json={"archive": 1},
            )
            if resp.status_code != 200:
                logger.warning(
                    f"Wallabag archive entry {entry_id} failed: "
                    f"HTTP {resp.status_code} - {resp.text[:200]}"
                )
                resp.raise_for_status()

            # Add tag
            tag = self.settings.wallabag_tag_on_process
            if tag:
                resp = await client.post(
                    f"{base}/api/entries/{entry_id}/tags.json",
                    headers=headers,
                    json={"tags": tag},
                )
                if resp.status_code != 200:
                    logger.warning(
                        f"Wallabag tag entry {entry_id} failed: "
                        f"HTTP {resp.status_code} - {resp.text[:200]}"
                    )

        logger.debug(f"Marked Wallabag entry {entry_id} as processed")
