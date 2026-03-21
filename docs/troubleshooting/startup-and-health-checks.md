# Startup and Health Checks

Use this page when Ghostwriter does not start cleanly, the UI does not load, or digests do not appear after startup.

## First Checks

### 1. Confirm the Container or Server Is Running

Docker:

```bash
cd ghostwriter
docker compose ps
```

### 2. Check the Health Endpoint

```bash
curl http://localhost:8080/health
```

Expected response:

```json
{"status":"healthy"}
```

### 3. Open the Web UI

If the health check works but the UI does not load, confirm you are using the same host and port in the browser.

## Logs

For Docker deployments:

```bash
docker logs -f ghostwriter
```

Look for:

- missing environment variables
- AI provider configuration errors
- migration failures
- port conflicts

## Common Causes

- `.env` was not copied or edited
- AI provider key is missing
- another service already uses port `8080`
- the container started but migrations or startup tasks failed

## Next Diagnostic Page

- If startup fails around AI configuration, go to [AI provider issues](ai-provider-issues.md).
- If startup works but login or device sync fails, go to [Sync and auth](sync-and-auth.md).
