# REVIEW-BACKEND-PUBLICATION

## Outcome

- The digest cap now applies to the final eligible batch in a stable source order: configured RSS order, Wallabag fetch order, newsletter fetch order, then completed media ordered by creation time and ID. Concurrent summary completion no longer changes Wallabag/newsletter order. Only included eligible items are marked seen, acknowledged, or consumed; excluded items remain available for another edition. Filtered items retain their existing seen behavior.
- Synthetic-feed setup and digest/config reads now run inside the pipeline's persisted failure boundary. Ordinary one-shot read failures leave the digest failed and unlocked, and a new run can retry.
- Deletion rejects another digest's EPUB or derived PDF claim when names collide by case or Unicode normalization, and also rejects an existing-file identity collision. The digest and artifacts remain intact after a conflict.

## Verification

- Focused source combinations, recovery, and retention tests: `63 passed` before the last source-order/next-edition assertions.
- Full backend suite on final code: `414 passed` (3 existing dependency/runtime warnings).
- Import-order lint (`ruff check --select I`) and `git diff --check`: passed.

## Scope and limits

All tests used local fixtures without provider calls. Persistent database failure cannot be recorded into that same unavailable database; the recovery fixture covers ordinary transient read failures. Publication and acknowledgment remain atomic at the existing commit boundary.
