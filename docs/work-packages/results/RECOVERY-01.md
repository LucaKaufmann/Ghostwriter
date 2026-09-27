# RECOVERY-01 result

Status: investigated, evidence and design only. Base: `679bd909d5780e55be21d8ea5347e3ea6a9a54d3`. Branch: `codex/recovery-01-fault-contract`. No production implementation, schema, external provider call, merge or deployment.

Changed paths: `ghostwriter/tests/test_bindery_recovery.py`, `docs/decisions/digest-recovery.md`, this result. The test uses a disposable SQLite DB and synthetic files/remotes. It injects artifact, article, media, remote marker and final completion failures, plus cancellation/startup recovery and stale lock admission. The decision note correlates job status, rows, artifact, source markers and pipeline events, and gives one implementation-ready follow-up. It also records the RETENTION-02 seam: ownership and cleanup of abandoned EPUB/rows belong to the retention contract, while local publication/acknowledgement ordering belongs to recovery.

Verification from `ghostwriter/`, using the read-only ENV-01 venv:

- `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv/bin/python -m pytest -q --tb=short tests/test_bindery_recovery.py tests/test_bindery_seen_articles.py` — 9 passed, 1 upstream Starlette warning.
- `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv/bin/python -m ruff check tests/test_bindery_recovery.py` — passed after import-order correction.

Limits: restart is lifespan recovery against a temporary DB, not a killed process; remotes and EPUB bytes are synthetic, so this proves ordering/durability behavior rather than provider or reader compatibility. A full backend suite is the orchestrator's integrated check. No PR was created pending independent root review.
