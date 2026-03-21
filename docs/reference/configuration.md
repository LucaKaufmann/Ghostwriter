# Configuration Reference

Ghostwriter is primarily configured through environment variables. The source of truth is [`ghostwriter/.env.example`](../../ghostwriter/.env.example).

## Core Settings

### General

- `LOG_LEVEL`
- `TIMEZONE`
- `JWT_SECRET`

### AI Provider

- `AI_PROVIDER`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`

### Scheduling

- `SCHEDULE_ENABLED`
- `SCHEDULE_MORNING`
- `SCHEDULE_NOON`
- `SCHEDULE_EVENING`

### Limits

- `MAX_ARTICLES_PER_FEED`
- `MAX_ARTICLES_PER_DIGEST`
- `FETCH_TIMEOUT_SECONDS`
- `MAX_CONCURRENT_FETCHES`

### Security and Networking

- `ALLOW_PRIVATE_HOSTS`
- `CORS_ALLOW_ORIGINS`
- `CORS_ALLOW_CREDENTIALS`
- `ENABLE_API_DOCS`
- `TRUSTED_PROXY_HOSTS`
- `PODCAST_PUBLIC_BASE_URL`

### Retention and Cleanup

- `DIGEST_RETENTION_DAYS`
- `SEEN_ARTICLE_RETENTION_DAYS`

### Notifications

- `WEBHOOK_URL`
- `WEBHOOK_ON_COMPLETE`
- `WEBHOOK_ON_FAILURE`

## Auth Note

New deployments should use:

- first-user registration in the web UI
- username and password for the web UI
- `gw_...` API tokens for devices and integrations

The compose setup still maps `GHOSTWRITER_API_KEY` into the legacy `API_KEY` environment variable for backward compatibility. Treat that as migration support rather than the preferred setup model.

## Next Step

- For API auth behavior, read [API reference](api.md)
- For operational debugging, read [Sync and auth troubleshooting](../troubleshooting/sync-and-auth.md)
