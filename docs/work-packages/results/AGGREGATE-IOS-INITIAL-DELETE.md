# Aggregate iOS initial-delete follow-up

Base: `0591f1fbca88926c6e851faa0f10c86ab4c9e9ba`. Final source: `cfb270cd5429241bc5fde91f011db1e49ad9004f` on `codex/aggregate-ios-initial-delete` (commits `7491cf8`, `f3ac5fb`, `cfb270c`).

An empty first server snapshot no longer discards a queued delete independently of an earlier create. Reconciliation collapses a same-URL initial prefix ending in delete only when every collapsed intent is pending, unsent, non-legacy, and null-base, beginning with a complete create. A later re-add must be a complete null-base upsert before that prefix can be removed. Claimed, blocked, legacy, and versioned intents retain their ordered delete barrier. ACK handling rebases only the immediate pending successor. Live server projections in reconciliation, conflict handling, incremental pull, and explicit keep/discard resolution use the final retained same-scope delete or re-add to set the cached hidden flag. Server values still win, tombstones stay hidden, and successor statuses and sent payloads remain unchanged.

Disk-backed SwiftData tests cover rollback of the reconciliation save, reopening after coalescence and claimed ACKs, create/edit/delete and delete/re-add ordering, complete serialized payloads, versioned and rejected controls, and hidden state after each ACK. An existing server-row fixture proves that Apply Mine followed by head ACK keeps a later blocked delete hidden across reopen. The exported KMP use-case tests prove both that an initial create followed by delete causes no mutation POST and that a resolved head stays hidden through POST acknowledgement, incremental pull, and reopen. Conflict, re-add, tombstone, keep-server, and discard controls check the other server-projection paths.

Verification on iPhone 16 Plus, iOS 18.6, using the existing shared XCFramework and generated Tuist workspace:

- Baseline red regression: `aggregate-ios-initial-delete-red.log` reproduced a claimable create and missing delete after empty reconciliation.
- Review red regression: `aggregate-ios-initial-delete-review-red.log` reproduced an existing-server case in which ACK of an explicitly resolved head exposed a later blocked delete.
- End-to-end red regression: `aggregate-ios-initial-delete-pull-red.log` reproduced a later delete exposed by the exported use case's incremental pull after ACK.
- Final source: focused `FeedV2StoreTests` 53/53 (`aggregate-ios-initial-delete-projection-focused-final.log`), full `Epilogue-Workspace` unit suite excluding UI 195/195 (`aggregate-ios-initial-delete-workspace-projection-final.log`), and explicit App simulator build (`aggregate-ios-initial-delete-app-build-projection-final.log`) all passed.
- Independent Sol reviews found the two ACK/projection defects above; cumulative review `ios-initial-delete-full-review.json` at `cfb270c` found no remaining actionable defect.

The source test records a claimed create before the first empty reconciliation to exercise the conservative replay barrier. The normal exported use-case path verifies unsent coalescence. This does not assert physical server timing or change the shared wire contract.
