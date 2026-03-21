# Ghostwriter Installation with Docker

This is the main supported installation path for running Ghostwriter.

## Prerequisites

- Docker
- Docker Compose
- An AI provider:
  - OpenAI
  - Google Gemini
  - Ollama

## What This Installs

The default compose setup provides:

- `ghostwriter` on port `8080`
- Persistent Docker volumes for:
  - application data
  - generated EPUB output
  - logs
- Optional Ollama sidecar with `--profile with-ollama`

## Installation

### 1. Prepare Configuration

```bash
cd ghostwriter
cp .env.example .env
```

At minimum, configure:

```bash
TIMEZONE=UTC
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
JWT_SECRET=change-this
```

Useful optional settings:

- `OPENAI_MODEL` or `GEMINI_MODEL`
- `SCHEDULE_ENABLED`, `SCHEDULE_MORNING`, `SCHEDULE_NOON`, `SCHEDULE_EVENING`
- `DIGEST_RETENTION_DAYS`
- `WEBHOOK_URL`
- `PODCAST_PUBLIC_BASE_URL`

## 2. Start the Stack

```bash
docker compose up -d
```

For local Ollama:

```bash
docker compose --profile with-ollama up -d
docker exec ollama ollama pull llama3.2
```

## 3. Verify Installation

Check the health endpoint:

```bash
curl http://localhost:8080/health
```

Then open:

```text
http://localhost:8080
```

## 4. First Login and Setup

On a new installation:

1. Open the web UI.
2. Register the first account.
3. Use that account as your admin account.
4. Create API tokens for mobile devices and integrations.

## Data and Persistence

The default compose file uses named Docker volumes:

- `ghostwriter_data`
- `ghostwriter_epubs`
- `ghostwriter_logs`

These hold:

- the database and app state
- generated digest files
- server and activity logs

If you switch to host-path mounts later, preserve the same persistence guarantees before removing the named volumes.

## Updating

Typical update flow:

```bash
cd ghostwriter
docker compose pull
docker compose up -d
```

The container entrypoint runs database migrations automatically on start.

## Next Step

- Continue with [Self-hosted quick start](../getting-started/self-hosted-quickstart.md)
- If startup fails, see [Startup and health checks](../troubleshooting/startup-and-health-checks.md)
