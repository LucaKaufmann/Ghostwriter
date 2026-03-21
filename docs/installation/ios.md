# iOS Installation and Availability

This repository contains the iOS app source, but this documentation set does not currently publish a stable public App Store or TestFlight link.

## Current Status

- The iOS client exists in this repository as `EpilogueIOS/`.
- Public installation channels are not documented here yet.
- Until a stable public distribution link is published, treat source builds as the documented path.

## What You Can Do Today

- If you are evaluating the project as a user, start with the self-hosted backend and web UI first.
- If you are building from source, use the iOS project README:
  - [Epilogue iOS README](../../EpilogueIOS/README.md)

## Expected Connection Flow

When an iOS build is installed, it should connect using:

- Ghostwriter server URL
- A per-device `gw_...` API token created in the web UI

For that flow, see [Connect mobile apps](../getting-started/connect-mobile-apps.md).

## Next Step

- For source setup, use [Epilogue iOS README](../../EpilogueIOS/README.md)
- For server pairing, use [API tokens and sync](../user-guide/api-tokens-and-sync.md)
