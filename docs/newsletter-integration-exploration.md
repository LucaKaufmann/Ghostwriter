# Newsletter Integration for Ghostwriter - Exploration & Discovery

## Goal

Enable Ghostwriter to receive newsletter emails and include them in the next scheduled digest, alongside existing RSS/Atom feed articles.

---

## Current Architecture (Relevant Parts)

- **Pipeline:** `BinderyPipeline` runs 4 stages: Fetch → Extract → Enrich → Compile
- **Data model:** `Feed` (with `mode: raw|summarize`), `ProcessedArticle`, `DigestArticle`, `SeenArticle`
- **Content extraction:** Trafilatura for web articles, feedparser for RSS
- **Scheduler:** APScheduler with morning/noon/evening cron triggers
- **Database:** SQLite via SQLModel (SQLAlchemy + Pydantic)
- **API:** FastAPI with bearer token auth

The pipeline currently only knows about RSS feeds. Newsletter content would need to enter the pipeline as articles alongside feed articles.

---

## Approach Options

### Option A: Gmail API Polling (Recommended)

**How it works:**
1. Set up a Gmail filter that labels incoming newsletters (e.g., label `Newsletters`)
2. Ghostwriter periodically polls Gmail API for unread emails with that label
3. Parse email HTML content, extract the article body
4. Inject as articles into the digest pipeline
5. Mark emails as read after processing

**Pros:**
- No external services needed beyond Gmail + Google Cloud Console
- You already have Gmail; just add a filter/label
- Full control over which newsletters to include via Gmail filters
- Works behind NAT/firewall (no inbound connections needed)
- Free

**Cons:**
- OAuth 2.0 setup with token refresh (one-time complexity)
- Polling delay (but fine since digests are scheduled anyway)
- Gmail API quota: 250 units/user/second (more than enough)

**Dependencies to add:**
```
google-auth>=2.0.0
google-auth-oauthlib>=1.0.0
google-api-python-client>=2.0.0
```

**Gmail filter setup:**
- In Gmail: create a filter for newsletter senders → apply label `Ghostwriter`
- Or filter by `list:` header which most newsletters include

---

### Option B: Gmail API with Pub/Sub Push Notifications

**How it works:**
1. Same Gmail label/filter setup as Option A
2. Use Gmail `watch()` API + Google Cloud Pub/Sub to get push notifications on new emails
3. Ghostwriter receives notification, fetches the email, stores it for next digest

**Pros:**
- Near-real-time awareness of new newsletters
- No polling overhead

**Cons:**
- Requires Google Cloud Pub/Sub setup (topic, subscription)
- `watch()` must be re-called every 7 days
- Push requires a publicly accessible endpoint (problematic for NAS behind NAT)
- Can use pull subscription instead, but then you're back to polling
- Significantly more infrastructure complexity for minimal benefit

**Verdict:** Overkill. Since digests run on a schedule (morning/noon/evening), polling before each digest is sufficient.

---

### Option C: IMAP Polling

**How it works:**
1. Connect to Gmail via IMAP with app-specific password
2. Search for emails in a specific folder/label
3. Parse and extract content

**Pros:**
- Simpler auth (app password instead of OAuth)
- Python `imaplib` is built-in

**Cons:**
- Google requires OAuth for IMAP too (as of May 2022); app passwords only work with 2FA enabled
- Rougher email parsing compared to Gmail API which returns structured data
- Less reliable than Gmail API for filtering

**Verdict:** Gmail API is cleaner since Google already requires OAuth either way.

---

### Option D: Email-to-Webhook Service (CloudMailin, MailSlurp)

**How it works:**
1. Use a service like CloudMailin that gives you an email address
2. Forward newsletters to that address (or set up Gmail forwarding)
3. Service POSTs parsed email content to Ghostwriter's API endpoint

**Pros:**
- Real-time, push-based
- Email is pre-parsed (HTML extracted, attachments handled)
- No OAuth complexity

**Cons:**
- Requires Ghostwriter to be publicly accessible (NAS behind NAT is a problem)
- External service dependency
- CloudMailin free tier: 10k emails/month (plenty, but still a dependency)
- Monthly cost if exceeding free tier

**Verdict:** Good if Ghostwriter were cloud-hosted, but problematic for a NAS deployment behind NAT.

---

## Recommended Approach: Option A (Gmail API Polling)

This fits the existing architecture best: Ghostwriter already polls feeds on a schedule, and adding Gmail polling is the same pattern.

---

## Implementation Design

### New Database Model

```python
class Newsletter(SQLModel, table=True):
    id: uuid.UUID
    gmail_message_id: str  # Gmail message ID for dedup + marking read
    subject: str
    sender: str
    received_at: datetime
    content: str           # Extracted HTML body
    processed: bool = False  # Included in a digest already
    created_at: datetime
```

### New Service: `NewsletterService`

```python
class NewsletterService:
    """Polls Gmail for newsletter emails and extracts content."""

    async def authenticate(self) -> None:
        """Load OAuth credentials, refresh if needed."""

    async def fetch_new_newsletters(self) -> list[Newsletter]:
        """
        Query Gmail API for unread emails with the configured label.
        Parse email body (prefer HTML part, fall back to plain text).
        Store in database, mark as read in Gmail.
        """

    async def get_unprocessed(self) -> list[ProcessedArticle]:
        """
        Return newsletters not yet included in a digest,
        converted to ProcessedArticle format for the pipeline.
        """

    async def mark_processed(self, newsletter_ids: list[uuid.UUID]) -> None:
        """Mark newsletters as included in a digest."""
```

### Pipeline Integration

Modify `BinderyPipeline.run()` to add a newsletter fetch step in Stage 1 (Fetch):

```python
# Existing: fetch RSS feeds
feed_articles = await self._fetch_feeds(feeds)

# New: fetch newsletters
newsletter_articles = await self.newsletter_service.get_unprocessed()

# Merge into article list
all_articles = feed_articles + newsletter_articles
```

Newsletters would be treated as `mode="raw"` by default (full content preserved), since they're already curated content. Optionally allow `mode="summarize"` via a setting.

### Configuration (Environment Variables)

```bash
# Newsletter integration
NEWSLETTER_ENABLED=false
NEWSLETTER_GMAIL_LABEL=Ghostwriter    # Gmail label to watch
NEWSLETTER_MODE=raw                    # raw or summarize
NEWSLETTER_MAX_PER_DIGEST=20          # Cap per digest
```

### OAuth Credential Storage

Store Gmail OAuth tokens in the data directory:
- `data/gmail_credentials.json` (OAuth client config, from Google Cloud Console)
- `data/gmail_token.json` (refresh token, auto-generated after first auth)

### New API Endpoints

```
GET  /newsletters              # List fetched newsletters
POST /newsletters/auth/init    # Start OAuth flow (returns auth URL)
POST /newsletters/auth/callback?code=...  # Complete OAuth flow
POST /newsletters/fetch        # Manually trigger fetch
GET  /newsletters/status       # Auth status, last fetch, counts
```

### Setup Flow (One-Time)

1. Create a Google Cloud project and enable Gmail API
2. Create OAuth 2.0 credentials (Desktop app type)
3. Download `credentials.json`, place in `data/gmail_credentials.json`
4. Call `POST /newsletters/auth/init` → returns Google auth URL
5. Open URL in browser, grant access, copy the auth code
6. Call `POST /newsletters/auth/callback?code=...` → stores refresh token
7. Create a Gmail filter for newsletters → apply label `Ghostwriter`
8. Set `NEWSLETTER_ENABLED=true` and restart

### EPUB Integration

Newsletters would appear as a third section in the EPUB:
- Section 1: Briefings (AI summaries)
- Section 2: Full Articles (RSS fidelity mode)
- **Section 3: Newsletters**

Or interleaved with full articles, grouped by source.

---

## Email Content Extraction

Newsletter emails are HTML. The extraction approach:

1. Gmail API returns message parts with MIME types
2. Prefer `text/html` part, decode from base64
3. Use `BeautifulSoup` (already have Trafilatura which depends on it) to:
   - Strip tracking pixels (`<img>` with 1x1 dimensions or tracking domains)
   - Remove unsubscribe footers (heuristic: last `<table>` or `<div>` with "unsubscribe")
   - Clean inline styles that break e-ink rendering
4. Optionally run through Trafilatura for main content extraction (works well on newsletter HTML)

---

## Estimated Scope

| Component | Files |
|-----------|-------|
| Newsletter SQLModel | `app/data/models/newsletter.py` (new) |
| NewsletterService | `app/services/newsletter_service.py` (new) |
| Gmail auth endpoints | `app/api/newsletters.py` (new) |
| Pipeline integration | `app/worker/bindery.py` (modify) |
| EPUB section | `app/services/epub_generator.py` (modify) |
| Settings | `app/core/settings.py` (modify) |
| Dependencies | `requirements.txt` (modify) |
| Migration script | `scripts/migrate_add_newsletters.py` (new) |

---

## Open Questions

1. **Newsletter dedup across digests:** Should a newsletter only appear in one digest, or should it appear until explicitly dismissed? (Recommendation: once, mark as processed)
2. **HTML fidelity vs plain text:** Should we preserve newsletter HTML styling in the EPUB or strip to plain text? (Recommendation: strip to clean HTML, similar to RSS fidelity mode)
3. **Newsletter-specific summarization prompt:** If using briefing mode, should newsletters get a different AI prompt than RSS articles? (Recommendation: yes, newsletters tend to be longer and more curated)
4. **Multiple Gmail accounts:** Support one account initially, could expand later
5. **Auth on headless NAS:** The OAuth flow requires a browser. The init/callback API endpoints allow doing this from any device that can reach the NAS API

---

## Sources

- [Gmail API Push Notifications](https://developers.google.com/workspace/gmail/api/guides/push)
- [Gmail API Python Quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
- [Gmail API watch() Reference](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/watch)
- [How to Read Emails from Gmail API in Python](https://www.geeksforgeeks.org/python/how-to-read-emails-from-gmail-using-gmail-api-in-python/)
- [CloudMailin Email Webhooks](https://www.cloudmailin.com/blog/receive-email-webhook-email-events)
- [EmailEngine Webhooks](https://emailengine.app/webhooks)
- [Understanding Gmail Pub/Sub Notifications](https://medium.com/@eagnir/understanding-gmails-push-notifications-via-google-cloud-pub-sub-3a002f9350ef)
