# Ghostwriter

RSS digest generation service for Epilogue. Aggregates RSS feeds, extracts article content, generates AI summaries, and compiles them into daily EPUB digests.

## Features

- **Web UI** - Modern, responsive dashboard for configuration and monitoring
- **Wallabag Integration** - Include saved articles from a Wallabag instance
- **RSS/Atom Feed Aggregation** - Parse and deduplicate articles from multiple feeds
- **Content Extraction** - Clean article extraction via Trafilatura
- **AI Summarization** - Provider-agnostic AI via LiteLLM (OpenAI, Gemini, Ollama)
- **EPUB Generation** - Compile articles into e-reader friendly digests
- **Scheduled Jobs** - Automatic morning/noon/evening digest generation
- **Push Notifications (Optional)** - APNs (iOS) + FCM (Android) notification when a non-empty digest is ready
- **REST API** - Full API for feed management and digest downloads

## Quick Start

### With Docker (Recommended)

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your settings

# Start with local Ollama
docker compose up -d

# Pull the Ollama model (first time only)
docker exec ollama ollama pull llama3.2

# Verify health
curl http://localhost:8080/health
```

### Cloud AI Only (No Ollama)

```bash
# Set your API key
export OPENAI_API_KEY=sk-...

# Start without Ollama
docker compose -f docker-compose.cloud.yml up -d
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment
export AI_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434

# Run
uvicorn app.main:app --reload --port 8080
```

## API Reference

All API endpoints below are served under the `/api` prefix (for example: `GET /api/feeds`). For backwards compatibility, `GET /health` is also available at the root.

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

### Notifications

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/notifications/devices` | List registered devices for the current user |
| `POST` | `/notifications/devices` | Register/update a device token (upsert by `device_id`) |
| `DELETE` | `/notifications/devices/{device_id}` | Disable a device token (idempotent) |

## Configuration

All configuration via environment variables. See `.env.example` for full list.

### Key Settings

```bash
# AI Provider: openai, gemini, ollama
AI_PROVIDER=ollama

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

## Push Notifications (Optional)

Ghostwriter can send a push notification when a new **non-empty** digest is completed. The Epilogue apps can use this to trigger an immediate sync and (best-effort) background fetch.

How it works:

- When you enable the toggle in the mobile app, the app registers its device token against your Ghostwriter user via the API.
- When a digest completes (`status=completed` and `article_count > 0`), Ghostwriter sends a `digest_ready` push to all enabled devices.
- iOS: APNs alert notification with `content-available: 1` (best-effort background fetch plus a visible notification).
- Android: FCM data message; the app shows a local notification (if permitted) and schedules a sync.

### Prerequisites

- You need a push-capable client (the Epilogue apps in this repo include support).
- Push credentials must match the exact app build you are running:
  - iOS: `APNS_BUNDLE_ID` must match the iOS app bundle identifier, and sandbox vs production must match the app's `aps-environment`.
  - Android: `FCM_PROJECT_ID` must match the Firebase project used by the Android app build.
- Store push keys outside the repo and never commit them.

### iOS (APNs) Setup

1. In the Apple Developer portal:
   - Enable **Push Notifications** for your App ID (bundle identifier).
   - Create an APNs Authentication Key (`.p8`) with the **Apple Push Notifications service (APNs)** entitlement.
   - Note your **Team ID** and the key's **Key ID**.
2. Copy the `.p8` file to the machine running Ghostwriter (do not commit it).
3. Set the APNs environment variables (e.g., in `.env`):

```bash
APNS_TEAM_ID=YOUR_TEAM_ID
APNS_KEY_ID=YOUR_KEY_ID
APNS_PRIVATE_KEY_PATH=/run/secrets/apns.p8
APNS_BUNDLE_ID=com.your.bundle.id
# true for Debug/dev builds, false for TestFlight/App Store builds
APNS_USE_SANDBOX=true
```

4. If you run Ghostwriter with Docker, mount the key into the container and make the path match `APNS_PRIVATE_KEY_PATH`:

```yaml
services:
  ghostwriter:
    environment:
      - APNS_PRIVATE_KEY_PATH=/run/secrets/apns.p8
    volumes:
      - /absolute/path/to/AuthKey_XXXXXXXXXX.p8:/run/secrets/apns.p8:ro
```

5. Restart Ghostwriter.

### Android (FCM) Setup

1. Create a Firebase project and add an Android app.
2. Build your Android app with the matching Firebase config (`google-services.json`) so it can obtain FCM tokens.
3. Create a Firebase service account JSON key (used by Ghostwriter to send notifications):
   - Google Cloud Console → **IAM & Admin** → **Service Accounts** → select/create one → **Keys** → **Add key** → **JSON**
4. Copy the JSON key to the machine running Ghostwriter (do not commit it).
5. Set the FCM environment variables:

```bash
FCM_SERVICE_ACCOUNT_PATH=/run/secrets/fcm-service-account.json
FCM_PROJECT_ID=your-firebase-project-id
```

6. If you run Ghostwriter with Docker, mount the JSON file into the container:

```yaml
services:
  ghostwriter:
    environment:
      - FCM_SERVICE_ACCOUNT_PATH=/run/secrets/fcm-service-account.json
    volumes:
      - /absolute/path/to/fcm-service-account.json:/run/secrets/fcm-service-account.json:ro
```

7. Restart Ghostwriter.

### Enable In The App

1. Configure Ghostwriter in the app (URL + API token).
2. Go to **Settings** → **Ghostwriter** → **Notifications**.
3. Enable the toggle and accept the OS permission prompt.
4. Trigger a digest (or wait for the schedule) and verify you receive a notification.

### Troubleshooting

- Verify a device registered successfully:
  - `GET /api/notifications/devices` (requires auth)
- iOS `BadDeviceToken` usually means a sandbox vs production mismatch (`APNS_USE_SANDBOX` vs the app's `aps-environment`).
- If you are behind a reverse proxy, the Ghostwriter host must still be able to reach APNs/FCM over outbound HTTPS.

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

MIT
