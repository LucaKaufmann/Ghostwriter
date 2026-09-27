# Negative article-limit wire boundary proof

PR106 review [4117040759](https://github.com/LucaKaufmann/Ghostwriter/pull/106#discussion_r4117040759) inferred that a decoded negative Kotlin Int could enter native state. Product source already rejects negative `maxArticles` in `FeedSnapshotV2.isValidV2`; the shared use case applies that validation before reconciliation, incremental writes and mutation acknowledgement. No product fix was needed.

Test-only source `dd244e7` plus fixture correction `b247ebb`, integrated as `264fde1/8a55776`, adds actual MockEngine JSON through `GhostwriterApiClient` and `FeedSyncV2UseCase`. Negative full-pull rows cannot bind/reconcile/claim, negative incremental rows cannot apply or advance the cursor, and negative applied receipts cannot acknowledge or consume a pending proposal. Each path includes a zero-cap valid control. Valid controls use monotonic server versions; no valid earlier acknowledgement is rolled back by an unrelated later pull failure.

Verification:

- Full shared Android at `dd244e7`: 62 passed, one intentional live-test skip; iOS simulator shared: 62 passed, no skips. Logs `negative-cap-shared-{android,ios}.log`.
- After the control-version correction at `b247ebb`, the entire affected use-case class passed again on Android and iOS simulator: 25/25 each. Logs `negative-cap-focused-final-{android,ios}.log`. Other tests and all product source were unchanged.
- Independent Sol branch review against `2918931` returned no findings, exit0: `negative-cap-boundary-proof-review.log/json`.
- Root compared the integrated tree to hosted-green `2918931994a05c3fb2d0e1f9e812556361fef479`, excluding only docs and shared common tests: no differences. Existing app, framework, backend and live integration gates remain applicable; they were not redundantly repeated for these fixtures.

All logs reside in `/private/tmp/epilogue-backlog-20260927/`. Fixtures use synthetic JSON and no production sources or providers. This is test evidence for the existing validation boundary, not a new schema or behavior change.
