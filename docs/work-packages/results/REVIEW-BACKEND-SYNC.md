# REVIEW-BACKEND-SYNC

## Outcome

- A valid legacy API key without a user account receives account-only 403 without a `WWW-Authenticate` challenge; missing/invalid credentials remain 401.
- Feed URL validation for web create/update and legacy sync runs through the bounded async DNS admission path. Active duplicate creates return 409 before DNS. The read transaction is rolled back before create/update validation, so slow DNS does not hold the feed writer lock. A DNS deadline returns 504 without persisting a feed.
- DNS admission transfers each freed slot to one FIFO waiter. Cancellation removes queued waiters or passes a reserved slot to the next waiter; no DNS worker outlives its slot accounting.
- Incremental `/api/feeds/changes-v2` pulls require the server instance ID. Successful v2 pulls record client feed activity; malformed/mismatched requests do not.

## Verification

- Focused auth/feed/DNS tests: `55 passed`.
- Full backend suite after implementation: `413 passed` (3 existing dependency/runtime warnings).
- Added deadline and FIFO/cancellation focused checks after full suite: `4 passed`.
- Import-order lint (`ruff check --select I`) and `git diff --check`: passed.

## Scope and limits

No production provider or external network request was made. DNS validation still cannot pin a later transport resolution; each outbound fetch continues validating every connection/redirect under its total timeout. The final deadline fixture was added after the full suite; its focused run passed and no production behavior changed after the full-suite run.
