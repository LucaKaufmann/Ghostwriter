# API Reference

Ghostwriter exposes its backend under the `/api` prefix.

## Interactive API Docs

Interactive FastAPI docs are disabled by default. To enable them, set:

```bash
ENABLE_API_DOCS=true
```

Then use:

- `/docs`
- `/redoc`
- `/openapi.json`

## Common Endpoints

### Public and setup

- `GET /health`
- `GET /api/health`
- `GET /api/auth/status`
- `POST /api/auth/register`
- `POST /api/auth/login`

### Authenticated areas

- feed management
- digest generation and history
- configuration
- API token management
- integrations
- podcast generation

## Auth Headers

Most authenticated API access uses either:

- `Authorization: Bearer <token>`
- `X-API-Key: <token>`

For regular user-facing setup, prefer API tokens created in the web UI.

## Related Pages

- [API tokens and sync](../user-guide/api-tokens-and-sync.md)
- [Configuration reference](configuration.md)
