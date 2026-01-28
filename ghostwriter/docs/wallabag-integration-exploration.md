# Wallabag Integration for Ghostwriter — Exploration Document

## Goal

When a digest is generated, Ghostwriter should also fetch unread articles from a configured Wallabag instance and include them alongside RSS feed articles in the EPUB output.

---

## How Wallabag's API Works

### Authentication

Wallabag uses OAuth2 with password grant:

1. Register an API client at `https://<instance>/developer/client/create` → get `client_id` + `client_secret`
2. Request a token:
   ```
   POST /oauth/v2/token
   { grant_type: "password", client_id, client_secret, username, password }
   ```
3. Response contains `access_token` (1h TTL) and `refresh_token`
4. All requests use `Authorization: Bearer <access_token>`

### Fetching Unread Articles

```
GET /api/entries?archive=0&sort=created&order=desc&perPage=100
```

Response includes `_embedded.items[]` with: `id`, `title`, `url`, `content` (full HTML), `domain_name`, `reading_time`, `tags[]`, `created_at`. Pagination via `page` param; total pages in response.

**Key detail:** The listing endpoint includes `content` (full extracted HTML) — Wallabag already does its own readability extraction on save. This means we can skip Trafilatura for Wallabag articles entirely.

### Marking as Processed

```
PATCH /api/entries/{id}  { "archive": 1 }
```

Or add a tag like `ghostwriter-processed` for non-destructive tracking:
```
POST /api/entries/{id}/tags  { "tags": "ghostwriter-processed" }
```

### Other Useful Endpoints

- `GET /api/entries/exists?url={url}` — dedup check
- `GET /api/entries?tags=some-tag` — fetch only tagged articles
- `since` param (unix timestamp) — fetch only articles saved after a date

---

## Integration Design

### Where It Fits in the Pipeline

The current Bindery pipeline has 4 stages: **Fetching → Extracting → Enriching → Compiling**.

Wallabag articles slot into the pipeline at the **Fetching** stage, right after RSS feeds are processed. Since Wallabag already provides extracted HTML content, these articles can skip the Extracting stage and go directly to Enriching (if summarization is desired) or straight to Compiling.

```
Stage 1: FETCHING
  ├── RSS feeds (existing) → ParsedArticles
  └── Wallabag (new)       → ParsedArticles (with content already attached)

Stage 2: EXTRACTING
  ├── RSS articles → Trafilatura
  └── Wallabag articles → SKIP (content already extracted)

Stage 3: ENRICHING
  └── All articles with mode="summarize" → LLM

Stage 4: COMPILING
  └── All articles → EPUB
```

### Configuration

Add to environment / `Settings` in `app/core/config.py`:

```python
# Wallabag integration (all optional — feature disabled if url is empty)
wallabag_url: str = ""            # e.g. "https://app.wallabag.it"
wallabag_client_id: str = ""
wallabag_client_secret: str = ""
wallabag_username: str = ""
wallabag_password: str = ""
wallabag_mode: str = "raw"        # "raw" or "summarize"
wallabag_max_articles: int = 20
wallabag_tag_filter: str = ""     # optional: only fetch articles with this tag
wallabag_tag_on_process: str = "ghostwriter"  # tag added after including in digest
```

### New Service: `app/services/wallabag_service.py`

Responsibilities:
- OAuth2 token management (obtain + refresh)
- Fetch unread articles, paginated
- Deduplicate against `seen_articles` (using wallabag entry ID as guid)
- Mark articles as archived after digest completion
- Return articles in the same `ParsedArticle`-compatible format the pipeline expects

Sketch:

```python
import httpx
from app.core.config import get_settings

class WallabagService:
    def __init__(self):
        self.settings = get_settings()
        self._token: str | None = None
        self._token_expires: float = 0
        self._refresh_token: str | None = None

    @property
    def is_configured(self) -> bool:
        s = self.settings
        return bool(s.wallabag_url and s.wallabag_client_id and s.wallabag_username)

    async def _ensure_token(self):
        if self._token and time.time() < self._token_expires - 60:
            return
        # POST /oauth/v2/token (or refresh if we have a refresh_token)
        ...

    async def fetch_unread_articles(self, max_articles: int = 20) -> list[dict]:
        """Fetch unread articles from Wallabag. Returns dicts with
        id, title, url, content (HTML), domain_name, reading_time."""
        await self._ensure_token()
        articles = []
        page = 1
        while len(articles) < max_articles:
            params = {"archive": 0, "perPage": min(max_articles - len(articles), 100),
                      "page": page, "sort": "created", "order": "desc"}
            if self.settings.wallabag_tag_filter:
                params["tags"] = self.settings.wallabag_tag_filter
            resp = await self._get("/api/entries", params=params)
            items = resp["_embedded"]["items"]
            articles.extend(items)
            if page >= resp["pages"]:
                break
            page += 1
        return articles[:max_articles]

    async def archive_article(self, entry_id: int):
        await self._patch(f"/api/entries/{entry_id}", json={"archive": 1})
```

### Changes to Bindery (`app/worker/bindery.py`)

In the fetching stage, after RSS feeds are collected:

```python
# After existing RSS fetch loop
wallabag = WallabagService()
if wallabag.is_configured:
    wb_articles = await wallabag.fetch_unread_articles(
        max_articles=settings.wallabag_max_articles
    )
    for article in wb_articles:
        guid = f"wallabag-{article['id']}"
        if await is_seen(guid):
            continue
        parsed_articles.append(ParsedArticle(
            guid=guid,
            url=article["url"],
            title=article["title"],
            author=article.get("domain_name", ""),
            content=article["content"],       # Already extracted HTML
            source_type="wallabag",
            wallabag_id=article["id"],
        ))
```

In the extracting stage, skip Trafilatura for Wallabag articles:

```python
if article.source_type == "wallabag":
    # Content already present from Wallabag's extraction
    pass
else:
    content = await trafilatura_extract(article.url)
```

After successful digest compilation, archive the Wallabag articles:

```python
if settings.wallabag_archive_after:
    for article in wallabag_articles:
        await wallabag.archive_article(article.wallabag_id)
```

### Deduplication

Use the `seen_articles` table with `guid = "wallabag-{entry_id}"` and a synthetic `feed_id` (e.g., a fixed UUID for the Wallabag source). This reuses the existing 30-day dedup window.

### EPUB Placement

Wallabag articles would appear as a separate section in the EPUB, similar to how RSS articles are grouped. The section could be titled "Saved Articles" or "From Wallabag". Alternatively, they can be interleaved with RSS articles — this is a UX choice.

---

## Considerations

**Content quality:** Wallabag's built-in extraction is generally good but sometimes captures navigation/junk. We could optionally re-extract with Trafilatura if quality is poor, but starting with Wallabag's content is simpler and avoids extra HTTP requests.

**Tag-based workflows:** A useful pattern is to configure `wallabag_tag_filter = "digest"` so users explicitly tag articles they want in the digest, rather than including all unread articles.

**Token storage:** OAuth tokens are ephemeral (1h). The service should handle refresh transparently. Credentials (username/password/client secret) are stored as environment variables, consistent with how `GEMINI_API_KEY` etc. are already handled.

**Failure isolation:** If Wallabag is unreachable, the digest should still generate from RSS feeds. Wallabag errors should be logged but not fail the pipeline.

**No new dependencies needed.** `httpx` is already available in the ghostwriter environment. The Wallabag API is standard REST/JSON — no client library needed.

---

## Summary of Changes

| File | Change |
|------|--------|
| `app/core/config.py` | Add wallabag env vars to Settings |
| `app/services/wallabag_service.py` | **New file** — OAuth + fetch + archive |
| `app/worker/bindery.py` | Call WallabagService in fetching stage, skip extraction for wallabag articles, archive after compile |
| `app/models/seen_article.py` | No schema change (use existing guid field) |
| `app/services/epub_generator.py` | Optional: add "Saved Articles" section heading |
| `docker-compose.yml` | Add wallabag env vars to container |

Estimated scope: ~150-200 lines of new code, ~30 lines of modifications to existing files.
