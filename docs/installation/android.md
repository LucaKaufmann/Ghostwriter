# Android Installation and Availability

This repository contains the Android app source, but this documentation set does not currently publish a stable public Google Play or direct download link.

## Current Status

- The Android client exists in this repository under `app/`.
- Public release channels are not documented here yet.
- Until that changes, the documented path is building from source.

## What You Can Do Today

- Start with the self-hosted Ghostwriter backend and validate the server flow first.
- If you want to install the Android client from source, use the root Android build instructions in:
  - [Root README development section](../../CONTRIBUTING.md)

## Expected Connection Flow

When an Android build is installed, it should connect using:

- Ghostwriter server URL
- A per-device `gw_...` API token created in the web UI

For that flow, see [Connect mobile apps](../getting-started/connect-mobile-apps.md).

## Next Step

- For auth and token lifecycle, read [API tokens and sync](../user-guide/api-tokens-and-sync.md)
- For the main supported server install path, read [Ghostwriter with Docker](ghostwriter-docker.md)
