# REVIEW-ONEOFF-OWNERSHIP

## Result

One-off digests now persist their user owner at creation, independently of a podcast episode. Deleting the last episode no longer removes the owner's ability to read or delete the digest. Other users, including administrators, receive 404; installation-wide digest lists and sync omit these private digests, including zero-article rows. An episode still referencing a digest continues to block manual deletion.

Migration 028 adds the nullable owner column and backfills only existing one-off episode `digest_ids` references with one valid, unambiguous owner. Conflicting, null-owner, malformed, missing-user, and unreferenced historical digests are left unowned; private synthetic-feed digests without a provable owner remain inaccessible. The migration is idempotent and has a no-op SQLite downgrade. Current one-off creation always writes `digest_ids`; the migration does not infer ownership from `article_ids` alone or the current caller.

The podcast preferences fallback also accepts the exact account-required 403 returned for a valid legacy API key when no user accounts exist. Invalid keys remain 401 and other authorization failures remain 403.

## Verification

- Full Ghostwriter backend suite reached 431 passed twice; the remaining failures were successive errors in migration test assertions (stale 027 fresh-head expectation, then `dict(CursorResult)` conversion). Both assertions were corrected; final focused migration and legacy no-user suite: 5 passed. No application or migration behavior failed in the full run.
- Focused one-off API fixtures passed before the full suite.
- New files pass `ruff check`; `git diff --check` passes. Existing FastAPI `Depends`/`Query` lint findings in modified legacy modules were outside this change.

## Limits

An unclassifiable historical one-off digest without a live episode reference or durable owner remains private and cannot be recovered by guessing. This change does not expose the owner in API responses or alter normal digest tenancy.
