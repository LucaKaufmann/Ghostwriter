# Aggregate iOS initial-delete follow-up

Base: `0591f1fbca88926c6e851faa0f10c86ab4c9e9ba`. Final source: `f3ac5fb1c387f0a1b600330a165b3fd0368d8197` on `codex/aggregate-ios-initial-delete` (initial fix `7491cf899ba6b32673697759575685633ddf8083`).

An empty first server snapshot no longer discards a queued delete independently of an earlier create. Reconciliation collapses a same-URL initial prefix ending in delete only when every collapsed intent is pending, unsent, non-legacy, and null-base, beginning with a complete create. A later re-add must be a complete null-base upsert before that prefix can be removed. Claimed, blocked, legacy, and versioned intents retain their ordered delete barrier. ACK handling rebases only the immediate pending successor; the final queued delete or re-add determines the cached hidden state even when later intents need resolution. Successor values and sent payloads remain unchanged.

Disk-backed SwiftData tests cover rollback of the reconciliation save, reopening after coalescence and claimed ACKs, create/edit/delete and delete/re-add ordering, complete serialized payloads, versioned and rejected controls, and hidden state after each ACK. An existing server-row fixture proves that Apply Mine followed by head ACK keeps a later blocked delete hidden across reopen. The exported KMP use-case test checks that an initial create followed by delete causes no mutation POST.

Verification on iPhone 16 Plus, iOS 18.6, using the existing shared XCFramework and generated Tuist workspace:

- Baseline red regression: `aggregate-ios-initial-delete-red.log` reproduced a claimable create and missing delete after empty reconciliation.
- Review red regression: `aggregate-ios-initial-delete-review-red.log` reproduced an existing-server case in which ACK of an explicitly resolved head exposed a later blocked delete.
- Initial source gates: focused `FeedV2StoreTests` 48/48, full App 94/94, App simulator build, and full workspace 190/190 passed. These precede the review correction and are recorded in the matching `aggregate-ios-initial-delete-{focused-final,app-test,app-build,workspace-test}.log` files.
- Final corrected source: focused `FeedV2StoreTests` 49/49 (`aggregate-ios-initial-delete-focused-correction.log`), full `Epilogue-Workspace` unit suite excluding UI 191/191 (`aggregate-ios-initial-delete-workspace-final.log`), and explicit App simulator build (`aggregate-ios-initial-delete-app-build-final.log`) all passed.

The source test records a claimed create before the first empty reconciliation to exercise the conservative replay barrier. The normal exported use-case path verifies unsent coalescence. This does not assert physical server timing or change the shared wire contract.
