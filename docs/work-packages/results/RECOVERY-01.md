# RECOVERY-01 result

Status: investigated, evidence and design only. Base: `679bd909d5780e55be21d8ea5347e3ea6a9a54d3`. Branch: `codex/recovery-01-fault-contract`. No production implementation, schema, external provider call, merge or deployment.

Changed paths: `ghostwriter/tests/test_bindery_recovery.py`, `docs/decisions/digest-recovery.md`, this result. The test uses a disposable SQLite DB and synthetic files/remotes. It injects artifact, article, media, real final-transaction commit, and post-commit completion logger failures; models remote marker errors both before and after a mock effect; and covers cancellation before/after final commit, startup recovery and stale lock admission. The decision note correlates job status, rows, artifact, source markers and pipeline events, and gives one implementation-ready follow-up. It also records the RETENTION-02 seam: ownership and cleanup of abandoned EPUB/rows belong to the retention contract, while local publication/acknowledgement ordering belongs to recovery.

Verification from `ghostwriter/`, using the read-only ENV-01 venv:

- `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv/bin/python -m pytest -q --tb=short tests/test_bindery_recovery.py tests/test_bindery_seen_articles.py` — 12 passed, 1 upstream Starlette warning.
- `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv/bin/python -m ruff check tests/test_bindery_recovery.py` — passed.

Review correction: the original fixture replaced `_complete` before its transaction, so it missed both rollback inside the actual commit and an exception after commit. The revised fixture exposes the second case's failed status with nonzero article count and committed seen rows. The original remote mock also treated every thrown error as no effect; the revised test shows both outcomes and the decision note labels real remote outcome unknown.

Limits: restart is lifespan recovery against a temporary DB, not a killed process; remotes and EPUB bytes are synthetic, so this proves ordering/durability behavior rather than provider or reader compatibility. A full backend suite is the orchestrator's integrated check. No PR was created pending independent root review.

Final independent Sol review of corrected real-transaction fault injection and unknown remote outcomes returned no actionable findings. This PR is evidence/design; the atomic-publication and durable-ack implementation remains a separate centrally allocated follow-up.
