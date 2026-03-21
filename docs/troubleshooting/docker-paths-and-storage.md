# Docker Paths and Storage

Ghostwriter's default Docker setup uses named volumes so app state survives container restarts and upgrades.

## Default Persistent Volumes

- `ghostwriter_data`
- `ghostwriter_epubs`
- `ghostwriter_logs`

These cover:

- database and application state
- generated digest files
- log output

## If You Customize Volume Mounts

Keep persistence for all three categories:

- app data
- digest output
- logs

Do not switch to temporary container-only storage unless you are intentionally running a disposable test instance.

## Troubleshooting Storage Problems

Symptoms of bad storage configuration include:

- digests disappearing after restart
- login state or setup state resetting unexpectedly
- missing logs after a crash

## Related Pages

- [Ghostwriter Docker installation](../installation/ghostwriter-docker.md)
- [Startup and health checks](startup-and-health-checks.md)
