# Ghostwriter

RSS digest generation service for Epilogue. Aggregates RSS feeds, extracts article content, generates AI summaries, and compiles them into daily EPUB digests.

## Features

- **Web UI** - Modern, responsive dashboard for configuration and monitoring
- **Gmail Newsletters** - Include newsletter emails from a Gmail label via OAuth
- **Wallabag Integration** - Include saved articles from a Wallabag instance
- **RSS/Atom Feed Aggregation** - Parse and deduplicate articles from multiple feeds
- **Content Extraction** - Clean article extraction via Trafilatura
- **AI Summarization** - Provider-agnostic AI via LiteLLM (OpenAI, Gemini, or local Ollama)
- **EPUB Generation** - Compile articles into e-reader friendly digests
- **Scheduled Jobs** - Automatic morning/noon/evening digest generation
- **REST API** - Full API for feed management and digest downloads

## Quick Start

### With Docker (Recommended)

```bash
# Clone and configure
cp .env.example .env
# Edit .env — set AI_PROVIDER and your API key (e.g. OPENAI_API_KEY)

# Start Ghostwriter
docker compose up -d

# Verify health
curl http://localhost:8080/health
```

To use local Ollama instead of a cloud AI provider:

```bash
# Set AI_PROVIDER=ollama in .env, then:
docker compose --profile with-ollama up -d
docker exec ollama ollama pull llama3.2
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment
export AI_PROVIDER=openai
export OPENAI_API_KEY=sk-...

# Run
uvicorn app.main:app --reload --port 8080
```

### PDF Rendering Dependencies

Ghostwriter uses WeasyPrint for PDF rendering. In Docker this is preinstalled by the project `Dockerfile`.
Python dependencies pin `pydyf` to a WeasyPrint-compatible range to avoid rendering regressions.

For host-based local development (outside Docker), ensure these system libraries are installed:
- `cairo`
- `pango`
- `gdk-pixbuf`
- system fonts (for example DejaVu)

## API Reference

### Feeds

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/feeds` | List all feeds |
| `POST` | `/feeds` | Create a feed |
| `POST` | `/feeds/sync` | Bulk sync from client |
| `DELETE` | `/feeds/{id}` | Remove a feed |

### Digests

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/digests/trigger` | Start manual digest |
| `GET` | `/digests` | List digests |
| `GET` | `/digests/latest` | Get latest completed |
| `GET` | `/digests/{id}/status` | Poll job progress |
| `GET` | `/digests/{filename}` | Download EPUB |
| `DELETE` | `/digests/{filename}` | Delete digest |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health |
| `GET` | `/config` | Current configuration |

## Configuration

All configuration via environment variables. See `.env.example` for full list.

### Key Settings

```bash
# AI Provider: openai, gemini, ollama
AI_PROVIDER=openai

# Transcription (local whisper.cpp and/or OpenAI Whisper API)
WHISPER_CPP_BINARY=/usr/local/bin/whisper-cli
WHISPER_MODELS_DIR=/app/data/models/whisper
WHISPER_TRANSCRIPTION_TIMEOUT_SECONDS=300
OPENAI_WHISPER_TIMEOUT_SECONDS=120

# Scheduling (24h format)
SCHEDULE_MORNING=07:00
SCHEDULE_EVENING=18:00

# Authentication (see below)
JWT_SECRET=your-secret-key-for-jwt-tokens

# Security / networking
ALLOW_PRIVATE_HOSTS=false
CORS_ALLOW_ORIGINS=https://ghostwriter.example.com
ENABLE_API_DOCS=false
TRUSTED_PROXY_HOSTS=203.0.113.10/32
AUTH_RATE_LIMIT_ENABLED=true
```

### whisper.cpp Binary Override (ARM / Raspberry Pi)

Ghostwriter's Docker image includes a bundled `whisper-cli` binary for local audio transcription (YouTube, podcasts). If transcription fails (for example with `Illegal instruction (core dumped)` on some ARM devices) or you want an optimized build for your specific CPU, you can provide your own binary via the data volume.

Ghostwriter resolves the whisper binary in this order:

1. `/app/data/bin/whisper-cli` (user override; persistent in the data volume)
2. `/usr/local/bin/whisper-cli` (bundled in the Docker image)
3. Not found (falls back to OpenAI Whisper API if provider is set to "auto")

Build and install your own binary:

```bash
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"

# Copy into your Ghostwriter data volume and make it executable:
cp build/bin/whisper-cli /path/to/ghostwriter/data/bin/whisper-cli
chmod +x /path/to/ghostwriter/data/bin/whisper-cli
```

## Authentication

Ghostwriter supports user accounts with secure authentication. On first run, you'll be prompted to create an admin account.

### User Accounts

- **Web UI**: Log in with username/password, receives a JWT token (valid 7 days)
- **Mobile Apps**: Create API tokens in Settings, use with `Authorization: Bearer <token>` or `X-API-Key: <token>`

### API Tokens

API tokens are designed for mobile apps and scripts:

1. Log into the web UI
2. Go to **Settings** → **API Tokens**
3. Click **Create Token** and give it a name (e.g., "My iPhone")
4. Copy the token immediately — it's only shown once!

Tokens start with `gw_` and are stored hashed in the database.

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_SECRET` | No | (auto-generated) | Secret key for JWT tokens. Set this for persistent sessions across restarts. |
| `API_KEY` | No | — | **Deprecated.** Legacy API key for backward compatibility. |

### Migration from Legacy API_KEY

If you're upgrading from a version that used `API_KEY`:

1. The legacy `API_KEY` continues to work for backward compatibility
2. Create a user account in the web UI (first user becomes admin)
3. Generate API tokens for your mobile apps
4. Remove `API_KEY` from your environment once migrated

A deprecation warning is logged when `API_KEY` is used.

### Security Notes

- Passwords are hashed with bcrypt
- JWT tokens expire after 7 days
- API tokens never expire but can be revoked
- If `JWT_SECRET` is not set, a random one is generated (tokens won't survive restarts)
- Download endpoints require `Authorization: Bearer <token>` (no query-string tokens)
- For public deployments, keep `ALLOW_PRIVATE_HOSTS=false` to avoid SSRF risks

## Web UI

Ghostwriter includes a built-in web interface for managing feeds, viewing digests, and configuring the service. The UI is automatically served when running the Docker image.

### Accessing the Web UI

After starting Ghostwriter, open `http://localhost:8080` in your browser. You'll be prompted for your API token (the `API_KEY` environment variable).

### Features

- **Dashboard** - Server status, active jobs, quick actions, recent digests
- **Feeds** - Add, search, and manage RSS/Atom feed subscriptions
- **Digests** - View history, download EPUBs, see article contents
- **Newsletters** - Connect Gmail to include newsletter emails
- **Settings** - Configure digest schedules, view AI settings

### Development

To run the frontend in development mode:

```bash
cd frontend
npm install
npm run dev
```

The development server proxies API requests to `http://localhost:8080`. Make sure the FastAPI backend is running.

### Building

The frontend is built automatically as part of the Docker image. To build manually:

```bash
cd frontend
npm run build
```

The built files are output to `frontend/build/` and served by FastAPI.

## Wallabag Integration

Ghostwriter can pull unread articles from a [Wallabag](https://wallabag.org) instance and include them in a dedicated "Saved Articles" section of the EPUB digest. After processing, articles are archived in Wallabag and tagged so they aren't fetched again.

### Setup

1. Log into your Wallabag instance and go to **API clients management** (`https://your-instance/developer`).
2. Create a new API client (any name, e.g. "Ghostwriter"). Copy the Client ID and Client Secret.
3. Set the following environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `WALLABAG_URL` | Yes | — | Your Wallabag instance URL (e.g. `https://wallabag.example.com`) |
| `WALLABAG_CLIENT_ID` | Yes | — | OAuth client ID from step 2 |
| `WALLABAG_CLIENT_SECRET` | Yes | — | OAuth client secret from step 2 |
| `WALLABAG_USERNAME` | Yes | — | Your Wallabag login username |
| `WALLABAG_PASSWORD` | Yes | — | Your Wallabag login password |
| `WALLABAG_MODE` | No | `raw` | `raw` keeps full article text, `summarize` runs AI summary |
| `WALLABAG_MAX_ARTICLES` | No | `20` | Maximum articles to include per digest |
| `WALLABAG_TAG_ON_PROCESS` | No | `ghostwriter` | Tag added to articles after processing |

If `WALLABAG_URL` or any of the credentials are empty, the integration is silently skipped.

### How it works

During each digest run, the pipeline:

1. Fetches unread (unarchived) articles from the Wallabag API
2. Deduplicates against previously seen articles
3. Optionally summarizes via AI (if `WALLABAG_MODE=summarize`)
4. Adds them as a "Saved Articles" section at the end of the EPUB
5. Archives each article in Wallabag and applies the configured tag

## Gmail Newsletter Integration

Ghostwriter can fetch unread emails from a Gmail label and include them in your digest. Emails are cleaned for e-ink (tracking pixels, scripts, and unsubscribe footers are stripped), then marked as read after processing.

### 1. Create a Google Cloud OAuth App

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a new project (or select an existing one).
2. Navigate to **APIs & Services** → **Library**, search for **Gmail API**, and click **Enable**.
3. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**.
   - Application type: **Web application**
   - Name: anything (e.g. "Ghostwriter")
   - Authorized redirect URIs: add your Ghostwriter callback URL:
     ```
     https://your-ghostwriter-host/newsletters/oauth/callback
     ```
     For local development, also add `http://localhost:8080/newsletters/oauth/callback`.
4. Copy the **Client ID** and **Client Secret**.
5. Go to **APIs & Services** → **OAuth consent screen**:
   - Add the Gmail scope: `https://www.googleapis.com/auth/gmail.modify`
   - Add yourself (and any other users) as **Test users** if the app is in "Testing" status

> **Important: Publishing status and token expiry**
>
> Google Cloud apps in **"Testing"** status have refresh tokens that expire after **7 days**. This means you'll need to re-authenticate weekly. To avoid this, publish your OAuth app to **"Production"** status (under OAuth consent screen → Publishing status). Since Ghostwriter only requests the `gmail.modify` scope, Google may require a brief verification process.

### 2. Configure Environment Variables

Set these in your `.env` or Docker environment:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GMAIL_CLIENT_ID` | Yes | — | OAuth client ID from step 1 |
| `GMAIL_CLIENT_SECRET` | Yes | — | OAuth client secret from step 1 |
| `GMAIL_LABEL` | No | `Ghostwriter` | Gmail label to fetch newsletters from |
| `GMAIL_MAX_ARTICLES` | No | `20` | Maximum emails to include per digest |

If `GMAIL_CLIENT_ID` or `GMAIL_CLIENT_SECRET` are empty, the integration is disabled.

### 3. Create a Gmail Label and Filter

In Gmail, create a label matching your `GMAIL_LABEL` value (default: **Ghostwriter**), then set up filters to automatically label incoming newsletters:

1. Open a newsletter email → click the three dots → **Filter messages like these**
2. Set the **From** address, click **Create filter**
3. Check **Apply the label** → select your label (e.g. "Ghostwriter")
4. Optionally check **Also apply filter to matching conversations** and **Skip the Inbox**

Repeat for each newsletter you want included in your digest.

### 4. Connect Gmail via the Web UI

1. Open the Ghostwriter web UI and go to **Newsletters** (or **Settings** → **Newsletters**)
2. Click **Connect Gmail** — a popup opens with the Google consent screen
3. Sign in and grant Ghostwriter access to read and modify your email
4. The popup closes automatically and the status updates to **Connected**

You can also trigger the OAuth flow programmatically via `POST /newsletters/oauth/init`, which returns an `auth_url` to open in a browser.

### 5. Test the Integration

Click **Preview** in the Newsletters page (or call `POST /newsletters/preview`) to fetch matching emails without marking them as read. This lets you verify the label and filters are working before running a real digest.

### How it Works

During each digest run, the pipeline:

1. Refreshes the OAuth access token using the stored refresh token
2. Queries Gmail for unread messages with the configured label
3. Parses each email from raw MIME format and cleans the HTML
4. Deduplicates against previously seen emails
5. Adds them to the digest alongside RSS and Wallabag articles
6. Marks all fetched emails as read via the Gmail batch API

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `401 Unauthorized` in logs | Refresh token expired (common with "Testing" apps) | Re-connect Gmail via the web UI. Consider publishing the OAuth app to "Production". |
| No emails fetched | Label doesn't match or no unread emails | Check `GMAIL_LABEL` matches exactly. Verify emails have the label and are unread. |
| `configured: false` in status | OAuth token was deleted after auth failure | Re-connect Gmail via the web UI. |
| Emails not cleaned well | Newsletter uses unusual HTML layout | Open an issue with the newsletter name — cleaning heuristics can be improved. |

## Architecture

```
app/
├── api/            # FastAPI routes
├── core/           # Config, database, security
├── models/         # SQLModel schemas
├── services/       # LLM, content processor, EPUB
└── worker/         # Bindery pipeline, scheduler
```

## License

[GPL-3.0](../LICENSE)
