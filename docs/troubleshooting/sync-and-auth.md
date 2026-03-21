# Sync and Auth

Use this page when login, token usage, or client sync is failing.

## First-Time Setup Problems

If you cannot create the first account:

- confirm this is a fresh deployment
- check whether a user already exists
- confirm the web UI is talking to the same Ghostwriter instance you intended to configure

Ghostwriter only allows open registration before the first user is created.

## Token Problems

If a client reports an invalid token:

- confirm the token starts with `gw_`
- create a fresh token in `Settings -> API Tokens`
- update the client with the new token
- avoid reusing copied or partially redacted values

## URL Problems

If one device works and another does not:

- compare the exact server URL on both devices
- verify whether one device is using a local URL and the other needs an external HTTPS URL
- check reverse proxy behavior if you are routing through another hostname

## Legacy API Key Notes

Ghostwriter still supports a legacy env-based API key path for backward compatibility, but new setups should rely on user accounts and per-device API tokens.

## Related Pages

- [API tokens and sync](../user-guide/api-tokens-and-sync.md)
- [Connect mobile apps](../getting-started/connect-mobile-apps.md)
