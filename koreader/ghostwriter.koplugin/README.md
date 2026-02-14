# ghostwriter.koplugin (MVP scaffold)

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
- Downloads new EPUBs incrementally.

## Install (manual)
1. Copy `ghostwriter.koplugin` into KOReader's `plugins/` directory.
2. Restart KOReader.
3. Open `Tools -> Ghostwriter`.
4. Configure URL/token/folder and run `Sync digests now`.

## Notes
- This is an MVP starter and should be validated on real KOReader hardware.
- Network/TLS behavior varies by device firmware; test against your deployment.
