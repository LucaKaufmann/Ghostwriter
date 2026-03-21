# Connect Mobile Apps

Connect mobile clients only after Ghostwriter is already running and you have created at least one API token.

## Before You Start

Make sure you already have:

- A running Ghostwriter instance
- A reachable server URL
- A `gw_...` API token created in `Settings -> API Tokens`

If not, finish [Self-hosted quick start](self-hosted-quickstart.md) first.

## Connection Details You Need

Most clients need:

- **Server URL**: for example `http://192.168.1.50:8080`
- **API token**: one token per device is recommended

If you connect from outside your home network, use a proper reverse proxy and HTTPS rather than exposing a raw local URL.

## iPhone and iPad

Current installation availability is documented in [iOS installation and availability](../installation/ios.md).

Once the app is installed:

1. Open the app settings.
2. Enter your Ghostwriter server URL.
3. Paste the API token you created for that device.
4. Trigger a sync and confirm digests appear.

## Android

Current installation availability is documented in [Android installation and availability](../installation/android.md).

Once the app is installed:

1. Open the app settings.
2. Enter your Ghostwriter server URL.
3. Paste the API token you created for that device.
4. Trigger a sync and confirm digests appear.

## Token Management Tips

- Use one token per device so you can revoke access without affecting everything else.
- Keep server URL and token pairs distinct for test and production servers.
- If a device stops syncing after token rotation, create a new token and update that device explicitly.

## Next Step

- For your first end-to-end test, continue with [First digest walkthrough](first-digest.md).
- For auth details and token lifecycle, read [API tokens and sync](../user-guide/api-tokens-and-sync.md).
