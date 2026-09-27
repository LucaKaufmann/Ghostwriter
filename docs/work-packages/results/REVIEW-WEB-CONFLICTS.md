# REVIEW-WEB-CONFLICTS plan and result

Base: `ddfe54be848f05c50d136a910822b52c38ded844`, branch `codex/review-web-conflicts`.

Plan:

- [x] Retain the most recent active 409 snapshot and merge only proposed fields onto it when a partial mutation later needs tombstone restoration.
- [x] Keep conflicts per operation and let retries update only their own entry; protect proposals from unrelated and delayed responses.
- [x] Scope Add/Edit/Delete dialog cleanup to the originating form session, preserving unrelated drafts.
- [x] Verify concurrent and delayed API responses in Playwright, run Svelte check/build and full browser suite, capture changed conflict UI.

Review: PR111 comments `4116017451`, `4116017457`, `4116017460`, and `4116017465` are addressed. Each conflict has a stable operation ID, its own retry action, and a pending state; simultaneous bulk failures and out-of-order responses keep all proposals reachable. A partial status retry carries the latest active server snapshot, updating it again if another active conflict follows, so a subsequent tombstone restore preserves the latest server title, mode, and limit while applying only the proposed status. Add, Edit, and Delete dialogs close/reset only when the completed mutation belongs to the currently displayed form session. A restore started from an edit cannot clear a later Add draft. Dismissal prevents an old retry response from reopening that proposal.

Verification: `npm run check` reported zero errors and warnings (`/private/tmp/review-web-conflicts-check-final.log`). The full `npm run test:e2e` suite passed **34/34**, including its production build and reviewed light/dark route snapshots (`/private/tmp/review-web-conflicts-full-final.log`). Thirteen feed-conflict browser cases include active→tombstone→active→tombstone restore, simultaneous conflicts, out-of-order 409, an unrelated open Edit dialog, and a delayed restore with a new Add draft. The changed conflict view is captured in [two concurrent proposals](assets/REVIEW-WEB-CONFLICTS-two-proposals.png). All browser APIs were mocked locally; no production requests were made.
