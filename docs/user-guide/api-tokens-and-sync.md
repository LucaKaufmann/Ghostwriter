# API Tokens and Sync

Ghostwriter supports modern account-based authentication with per-device API tokens.

## Recommended Auth Model

Use this flow:

1. Create the first admin account in the web UI.
2. Log in normally with username and password.
3. Create API tokens for mobile clients and integrations.

API tokens:

- start with `gw_`
- are shown only when created
- can be revoked later

## Where to Create Tokens

In the web UI:

1. Open `Settings`.
2. Open `API Tokens`.
3. Create one token per device or integration.

Examples:

- `iPhone`
- `Android tablet`
- `KOReader`

## How Clients Use Tokens

Clients typically authenticate with:

- `Authorization: Bearer <token>`
- or `X-API-Key: <token>`

The preferred user pattern is still one token per client.

## Sync Tips

- Give each device its own token.
- Revoke lost or retired devices instead of rotating every token at once.
- Keep server URLs consistent across clients so sync failures are easier to compare.

## Legacy Compatibility

Ghostwriter still has backward compatibility for the older single env-based API key path, but new deployments should use user accounts and API tokens.

## Related Pages

- [Connect mobile apps](../getting-started/connect-mobile-apps.md)
- [Sync and auth troubleshooting](../troubleshooting/sync-and-auth.md)
