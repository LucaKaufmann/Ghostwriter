# ghostwriter.koplugin

This is a KOReader plugin scaffold for syncing Ghostwriter digest EPUB files.

## Current behavior
- Configures:
  - Ghostwriter server URL
  - API token (`gw_...`)
  - Download folder
  - Keep-last-N retention
  - Optional sync on suspend
- Uses Ghostwriter endpoints:
  - `GET /api/digests/new?last_known_id=<uuid>`
  - `GET /api/digests/{filename}`
- Downloads new EPUBs incrementally. The cursor is scoped to the server and
  download folder and advances only after each contiguous successful download
  has been recorded in settings.
- Retention applies only to files downloaded and recorded by this plugin for
  the current server and folder. Existing EPUBs are never adopted. A missing
  or damaged ownership record cannot authorize deletion. The first sync after
  a missing record does not prune anything; later syncs may prune the newly
  recorded downloads. `Keep last N = 0` disables pruning.

## Install (manual)
1. Copy `ghostwriter.koplugin` into KOReader's `plugins/` directory.
2. Restart KOReader.
3. Open `Tools -> Ghostwriter`.
4. Configure URL/token/folder and run `Sync digests now`.

## Notes
- Choose a real, absolute folder without symlinked path components. A file
  already present at a digest's filename is preserved and reported as a failed
  download unless it still matches the plugin's ownership record. Remove or
  rename that collision manually before retrying. Existing installations may
  need to resolve such collisions once because older downloads were not
  recorded as plugin-owned.
- Host regression checks: `lua ghostwriter/koreader/tests/run.lua` from the
  repository root. The harness uses temporary files under `/private/tmp` and
  mocks the KOReader UI and Ghostwriter network calls; it requires host Lua
  and macOS `stat`.
- This is an MVP starter and should be validated on real KOReader hardware.
- Network/TLS behavior varies by device firmware; test against your deployment.
