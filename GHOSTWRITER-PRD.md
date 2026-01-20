
# Product Requirements Document: Ghostwriter Service

|**Document Details**|
|---|---|
|**Project Name**|Ghostwriter (Epilogue Backend)|
|**Version**|1.0.0|
|**Status**|**Ready for Implementation**|
|**Type**|Self-Hosted Backend Service|
|**Target Deployment**|Docker (NAS / Home Server)|

## 1. Executive Summary

**Ghostwriter** is a headless, self-hosted backend service designed to power the "Epilogue" e-reading ecosystem. It acts as an autonomous agent that aggregates RSS feeds, extracts article content, generates AI summaries using local or cloud providers, and compiles them into daily `.epub` digests. It solves the battery and network limitations of performing these heavy tasks directly on Android devices.

## 2. System Architecture

### 2.1 High-Level Diagram

Code snippet

```
graph TD
    A[Android App] -->|Sync Feeds & Config| B(Ghostwriter API)
    A -->|Download EPUB| B
    B -->|Store Data| C[(SQLite DB)]
    B -->|Fetch Content| D[Internet/RSS]
    B -->|Generate Summary| E[AI Service]
    E -.->|Option A| F[OpenAI / Gemini API]
    E -.->|Option B| G[Local Ollama Sidecar]
    B -->|Save File| H[Output Volume]
```

### 2.2 Technology Stack

- **Language:** Python 3.11+
    
- **Web Framework:** FastAPI (Async, Pydantic v2 integration)
    
- **Database:** SQLite + **SQLModel** (ORM)
    
- **Task Scheduling:** APScheduler (In-process background scheduler)
    
- **Content Parsing:** `trafilatura` (Article extraction), `feedparser`
    
- **Ebook Generation:** `EbookLib`
    
- **AI Orchestration:** **LiteLLM** (Universal adapter for OpenAI/Gemini/Ollama)
    

---

## 3. Functional Requirements

### 3.1 Feed Management

- **FR-1:** Endpoint to sync feed configurations from the Android client.
    
- **FR-2:** Support individual processing modes per feed:
    
    - `raw`: Extract full text only.
        
    - `summarize`: Extract text + Generate AI summary.
        

### 3.2 The "Bindery" Pipeline (Core Logic)

The digest generation process (The "Worker") must follow this sequence:

1. **Trigger:** Scheduled time (Morning/Noon/Evening) OR Manual API trigger.
    
2. **Fetch:** Pull RSS feeds; filter out items older than 24h or already seen.
    
3. **Extract:** Use `trafilatura` to get clean readable text from URLs.
    
4. **Enrich (AI):** If enabled, pass text to `LLMService` (see Sec 3.3).
    
5. **Compile:** Generate `.epub` with:
    
    - Cover Page (Dynamic date).
        
    - Table of Contents.
        
    - Chapters (grouped by Feed).
        
6. **Cleanup:** Prune old EPUBs (keep last 7 days by default).
    

### 3.3 AI Service ("The Ghostwriter")

- **FR-3:** System must be **provider agnostic**.
    
- **FR-4:** Configuration via Environment Variables determines the provider:
    
    - **Cloud:** OpenAI (`gpt-4o`), Google Gemini (`gemini-1.5-flash`).
        
    - **Local:** Ollama (`llama3.2`, `phi3`).
        
- **FR-5:** **Fail-Open Strategy:** If the AI service fails (timeout/error), the system **must** include the raw article text instead of failing the whole digest.
    

### 3.4 API Interface

#### Feed Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/feeds/sync` | Bulk update feed list (replaces all) |
| `GET` | `/feeds` | Return current feed configuration |
| `DELETE` | `/feeds/{id}` | Remove a single feed |

#### Digest Operations
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/digests/trigger` | Manually start a digest job |
| `GET` | `/digests` | List available digest files |
| `GET` | `/digests/latest` | Get most recent completed digest |
| `GET` | `/digests/{id}/status` | Poll job progress (see 3.4.1) |
| `GET` | `/digests/{filename}` | Download EPUB file |
| `DELETE` | `/digests/{filename}` | Delete a digest file |

#### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service status and version |
| `GET` | `/config` | Current schedule, AI provider, timezone |

#### 3.4.1 Job Status Response

The `/digests/{id}/status` endpoint returns real-time progress:

```json
{
  "id": "abc-123",
  "status": "processing",
  "stage": "enriching",
  "progress": {
    "total_feeds": 12,
    "feeds_fetched": 12,
    "total_articles": 34,
    "articles_enriched": 21
  },
  "started_at": "2024-10-24T07:00:00Z",
  "eta_seconds": 45
}
```

Stages: `queued` → `fetching` → `extracting` → `enriching` → `compiling` → `completed`

### 3.5 Authentication

- **FR-6:** API authentication via bearer token.
- **FR-7:** If `API_KEY` environment variable is empty, authentication is disabled (LAN-only deployments).
- **FR-8:** All endpoints except `/health` require authentication when enabled.

```
Authorization: Bearer <API_KEY>
```

### 3.6 Job Management

- **FR-9:** Only one digest job may run at a time. Concurrent triggers must be rejected with `409 Conflict`.
- **FR-10:** Jobs must implement row-level locking to prevent race conditions.
- **FR-11:** Stale locks (older than 30 minutes) should be auto-released on startup.

### 3.7 Notifications (Optional)

- **FR-12:** Support webhook notifications on job completion or failure.
- **FR-13:** Compatible with ntfy, Pushover, Home Assistant, or generic HTTP endpoints.

---

## 4. Database Schema (SQLModel)

### `Feed`

|**Field**|**Type**|**Notes**|
|---|---|---|
|`id`|UUID|PK|
|`url`|Str|Unique|
|`title`|Str||
|`is_active`|Bool|Default: `true`|
|`mode`|Str|`raw` or `summarize`|
|`max_articles`|Int|Per-run limit (default: 10)|
|`created_at`|DateTime||
|`updated_at`|DateTime||

### `Digest`

|**Field**|**Type**|**Notes**|
|---|---|---|
|`id`|UUID|PK|
|`filename`|Str|e.g., `2024-10-24_morning.epub`|
|`period`|Str|`morning`, `noon`, `evening`, or `manual`|
|`created_at`|DateTime||
|`completed_at`|DateTime|Null until finished|
|`status`|Str|`queued`, `processing`, `completed`, `failed`|
|`stage`|Str|Current pipeline stage (see 3.4.1)|
|`article_count`|Int||
|`error_message`|Str|Null unless failed|
|`locked_at`|DateTime|For job locking (null if not running)|
|`locked_by`|Str|Instance identifier|

### `SeenArticle` (Deduplication)

Tracks articles that have been processed to prevent duplicates across runs.

|**Field**|**Type**|**Notes**|
|---|---|---|
|`id`|UUID|PK|
|`feed_id`|UUID|FK → Feed|
|`guid`|Str|RSS GUID or URL hash|
|`url`|Str|Original article URL|
|`title`|Str|For debugging|
|`seen_at`|DateTime|First encountered|

**Index:** `(feed_id, guid)` for fast lookups.
**Retention:** Auto-delete entries older than `SEEN_ARTICLE_RETENTION_DAYS`.

### `DigestArticle` (Audit Trail)

Links articles to digests for history and debugging.

|**Field**|**Type**|**Notes**|
|---|---|---|
|`id`|UUID|PK|
|`digest_id`|UUID|FK → Digest|
|`feed_id`|UUID|FK → Feed|
|`title`|Str||
|`url`|Str||
|`mode`|Str|`raw` or `summarized`|
|`word_count`|Int||
|`ai_failed`|Bool|True if fell back to raw text|
|`processing_ms`|Int|Time spent on this article|

---

## 5. Configuration (Environment Variables)

The system must be configured entirely via `ENV` vars for Docker compatibility.

### 5.1 Core Settings

```bash
# General
LOG_LEVEL=INFO                     # DEBUG, INFO, WARNING, ERROR
TIMEZONE=Europe/London             # IANA timezone identifier
API_KEY=                           # Bearer token (empty = no auth)
```

### 5.2 AI Configuration

```bash
# Provider Selection: 'openai', 'gemini', 'ollama'
AI_PROVIDER=ollama

# Provider-Specific Keys
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini           # Default model for OpenAI
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-1.5-flash      # Default model for Gemini

# Ollama (Local)
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3.2

# AI Behavior
AI_TIMEOUT_SECONDS=60              # Per-article timeout
AI_MAX_RETRIES=2                   # Retries before fallback to raw
```

### 5.3 Scheduling

```bash
# 24h format, leave empty to disable a period
SCHEDULE_MORNING=07:00
SCHEDULE_NOON=12:00
SCHEDULE_EVENING=18:00
SCHEDULE_ENABLED=true              # Master switch for scheduled runs
```

### 5.4 Rate Limiting & Caps

```bash
FETCH_DELAY_MS=500                 # Delay between feed fetches
FETCH_TIMEOUT_SECONDS=30           # Per-feed fetch timeout
MAX_ARTICLES_PER_FEED=10           # Cap per feed per run
MAX_ARTICLES_PER_DIGEST=50         # Overall cap per digest
MAX_CONCURRENT_FETCHES=3           # Parallel feed fetches
```

### 5.5 Retention & Cleanup

```bash
DIGEST_RETENTION_DAYS=7            # Auto-delete old EPUBs
SEEN_ARTICLE_RETENTION_DAYS=30     # Deduplication window
```

### 5.6 Notifications (Optional)

```bash
WEBHOOK_URL=                       # e.g., https://ntfy.sh/my-topic
WEBHOOK_ON_COMPLETE=true           # Notify on successful digest
WEBHOOK_ON_FAILURE=true            # Notify on failed digest
```

---

## 6. Deployment

### 6.1 Docker Compose (Recommended)

```yaml
version: "3.8"

services:
  ghostwriter:
    image: ghcr.io/your-org/ghostwriter:latest
    container_name: ghostwriter
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - TIMEZONE=Europe/London
      - API_KEY=${GHOSTWRITER_API_KEY}
      - AI_PROVIDER=ollama
      - OLLAMA_BASE_URL=http://ollama:11434
      - OLLAMA_MODEL=llama3.2
      - SCHEDULE_MORNING=07:00
      - SCHEDULE_EVENING=18:00
      - SCHEDULE_NOON=
    volumes:
      - ghostwriter_data:/app/data      # SQLite database
      - ghostwriter_epubs:/app/output   # Generated EPUBs
    depends_on:
      - ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    volumes:
      - ollama_data:/root/.ollama
    # Uncomment for GPU passthrough (NVIDIA)
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

volumes:
  ghostwriter_data:
  ghostwriter_epubs:
  ollama_data:
```

### 6.2 Standalone (Cloud AI Only)

For deployments without local AI, Ollama can be omitted:

```yaml
version: "3.8"

services:
  ghostwriter:
    image: ghcr.io/your-org/ghostwriter:latest
    container_name: ghostwriter
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - TIMEZONE=America/New_York
      - API_KEY=${GHOSTWRITER_API_KEY}
      - AI_PROVIDER=openai
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./data:/app/data
      - ./epubs:/app/output
```

### 6.3 First-Time Setup

1. Pull the Ollama model (if using local AI):
   ```bash
   docker exec ollama ollama pull llama3.2
   ```

2. Verify the service is healthy:
   ```bash
   curl http://localhost:8080/health
   ```

3. Sync feeds from the Android app or manually:
   ```bash
   curl -X POST http://localhost:8080/feeds/sync \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '[{"url": "https://example.com/feed.xml", "title": "Example", "mode": "summarize"}]'
   ```

---

## 7. Non-Functional Requirements

### 7.1 Performance

- **NFR-1:** Digest generation must complete within 10 minutes for up to 50 articles.
- **NFR-2:** API responses (excluding downloads) must return within 500ms.
- **NFR-3:** Memory usage should stay under 512MB during normal operation.

### 7.2 Reliability

- **NFR-4:** Service must recover gracefully from container restarts (APScheduler persistence).
- **NFR-5:** Partial failures (single feed or article) must not fail the entire digest.
- **NFR-6:** Stale job locks must auto-release after 30 minutes.

### 7.3 Observability

- **NFR-7:** Structured JSON logging with correlation IDs per digest run.
- **NFR-8:** `/health` endpoint must report: uptime, last successful digest, queue status.
- **NFR-9:** Digest history retained for 30 days (metadata only, not EPUBs).

---

## 8. Future Considerations

The following are out of scope for v1.0 but may be considered:

- **Multi-user support** with per-user feed lists and API keys
- **Web UI** for feed management and digest preview
- **OPML import/export** for feed portability
- **Custom AI prompts** per feed for specialized summarization
- **Push notifications** via FCM to Android app when digest is ready
- **Incremental EPUB updates** (append new articles to existing digest)
