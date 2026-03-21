# Settings and Schedules

Ghostwriter combines environment-based server settings with runtime settings managed through the web UI.

## Server-Level Settings

These are typically configured in `ghostwriter/.env` before or during deployment:

- timezone
- AI provider and model
- scheduling defaults
- retention
- networking and security controls
- webhook and public URL settings

For the full list, read [Configuration reference](../reference/configuration.md).

## Runtime Settings

Use the web UI for day-to-day settings such as:

- account and API token management
- operational preferences exposed by the UI
- optional integrations such as Wallabag and newsletters

## Scheduling Strategy

Start simple:

- enable one schedule window first
- confirm a successful run
- then add additional schedule times if needed

Relevant schedule settings include:

- `SCHEDULE_ENABLED`
- `SCHEDULE_MORNING`
- `SCHEDULE_NOON`
- `SCHEDULE_EVENING`

## Good Defaults

- Pick one timezone and keep it accurate.
- Use small content caps while validating a new deployment.
- Avoid changing schedule windows and AI settings at the same time when debugging.

## Related Pages

- [Configuration reference](../reference/configuration.md)
- [Startup and health checks](../troubleshooting/startup-and-health-checks.md)
