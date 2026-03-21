# Self-Hosted Quick Start

This is the fastest supported path to a working Ghostwriter instance.

## Prerequisites

- Docker and Docker Compose
- One AI provider:
  - OpenAI API key
  - Google Gemini API key
  - Ollama if you want a local model

## 1. Prepare the Environment

```bash
cd ghostwriter
cp .env.example .env
```

Edit `.env` and set at least:

```bash
TIMEZONE=Europe/Helsinki
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
JWT_SECRET=change-this-to-a-long-random-string
```

Notes:

- Use `AI_PROVIDER=gemini` with `GEMINI_API_KEY` if you prefer Gemini.
- Use `AI_PROVIDER=ollama` if you want a local model and plan to start the Ollama sidecar.
- `JWT_SECRET` is strongly recommended so web sessions survive restarts.

## 2. Start Ghostwriter

```bash
docker compose up -d
```

If you want Ollama in the same compose stack:

```bash
docker compose --profile with-ollama up -d
```

## 3. Verify the Service

Check the health endpoint:

```bash
curl http://localhost:8080/health
```

Expected response:

```json
{"status":"healthy"}
```

Then open `http://localhost:8080`.

## 4. Create the First Admin Account

On first run, Ghostwriter allows one-time registration:

1. Open the web UI.
2. Create the first user account.
3. That first account becomes the admin account automatically.

After the first user exists, open registration closes and normal login is used.

## 5. Generate API Tokens

In the web UI:

1. Open `Settings`.
2. Open `API Tokens`.
3. Create a token for each mobile app or integration.
4. Copy each token immediately.

Ghostwriter API tokens start with `gw_` and are the preferred way to connect mobile clients and plugins.

## 6. Add a Feed

Once the server is healthy and you can log in:

1. Open the feeds area in the web UI.
2. Add one or two RSS or Atom feeds.
3. Confirm they sync successfully.

## Next Step

Continue with [Connect mobile apps](connect-mobile-apps.md) or go straight to [First digest walkthrough](first-digest.md).
