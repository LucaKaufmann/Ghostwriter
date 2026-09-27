# SYNC-EDITS-SERVER result

Implemented on frozen server base `df28f112ce14a2f1030173cbbcf05314c0f11453` with Alembic revision `026` after `025`.

- Added a persisted server instance UUID, global int64 feed change sequence, feed versions, and replay receipts. The v2 pull includes active rows and durable tombstones in version order; v2 mutation batches use per-item transactions and exact replay outcomes. Stale bases preserve the current server row and reject local writes.
- Restricted `/feeds/sync` to exact no-ops. Web PUT, DELETE and tombstone restore require quoted `If-Match` versions; web edit, toggle, bulk and delete actions now send the displayed version and show an explicit retry after conflict. Legacy read routes remain available and exclude synthetic feed rows.
- Preserved `max_articles=0` through v2 storage and parsing as unlimited per feed. Removed the 30-day feed tombstone purge while keeping the integrated digest-retention cleanup. Added restore identity rotation command and documented the v2 backup/restore and binary rollback boundary in `ghostwriter/RELEASE.md`.
- Reused the bounded DNS admission path for v2 URL validation before acquiring SQLite's write lock. Durable replays return without DNS; validation timeouts leave no write or receipt.

Verification: full Ghostwriter backend suite **381 passed** before the final bounded-DNS addition; focused feed/migration/outbound-fetch tests **44 passed** afterward. A gated-DNS test proves another mutation and `/api/health` progress while DNS is blocked, followed by timeout without a feed or receipt. Alembic previous-revision backfill, repeated `026`, fresh schema, and pre-mutation backup restore with identity rotation all pass. Frontend `npm run check` and `npm run build` pass; two focused Playwright browser tests pass, covering conflict retry and edit/bulk version headers. Screenshot: `/private/tmp/epilogue-backlog-20260927/sync-server-feed-conflict.png`. Targeted Ruff check passed with inherited `B008`/`UP045` API-style rules ignored.

No provider calls, deployment, native, KMP, recovery schema `027`, or bindery changes were made. Root still needs independent integration review and combined fixture checks before PR acceptance.
