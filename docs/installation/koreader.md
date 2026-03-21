# KOReader Installation

Ghostwriter includes an MVP KOReader plugin scaffold for syncing digest EPUB files.

## Current Status

- The plugin lives in `ghostwriter/koreader/ghostwriter.koplugin/`.
- Installation is currently manual.
- This is an MVP integration and should be validated on your hardware and firmware combination.

## What You Need

- A running Ghostwriter instance
- A `gw_...` API token
- KOReader with access to its `plugins/` directory

## Manual Install

1. Copy `ghostwriter.koplugin` into KOReader's `plugins/` directory.
2. Restart KOReader.
3. Open `Tools -> Ghostwriter`.
4. Configure:
   - Ghostwriter server URL
   - API token
   - download folder
   - retention settings
5. Run `Sync digests now`.

## Current Behavior

The plugin scaffold is designed to:

- download newly available digests incrementally
- store EPUBs in a chosen folder
- optionally sync on suspend

## Notes

- Network and TLS behavior can vary between KOReader devices and firmware versions.
- Test with a reachable local URL first before moving to a public deployment.

## Next Step

- For token setup, read [API tokens and sync](../user-guide/api-tokens-and-sync.md)
- For broader reader workflows, read [E-ink readers](../integrations/eink-readers.md)
