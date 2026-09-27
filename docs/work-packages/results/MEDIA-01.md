# MEDIA-01 result

Status: implementation verified locally; ready for orchestrator review.

- Base: `de68d540ea67383a3843b8085659d29dcf19baaa` (PR 75 integration base).
- Head: the scoped commit containing this result (exact SHA in orchestrator handoff).
- The original item-status guard allowed two concurrent runs to enter awaited discovery. A deterministic test on the unchanged base failed with two discovery calls and overlapping mocked transcriptions of two queued synthetic items.
- A process-local asyncio lock now covers stale-item release, the existing item-status guard, discovery, item processing, and run finalization. A concurrent trigger skips without creating a run record. Cancellation marks the active item failed, persists the run as failed with completion time and message, and propagates cancellation. The lock releases through its async context manager.
- Existing stale cutoff and API retry behavior remain unchanged. Tests cover subsequent retry after cancellation and a top-level discovery failure, stale-item release, and a feed-specific transient failure followed by successful discovery. No schema change.

## Verification

Python 3.11.16; isolated, read-only virtual environment from ENV-01. All media and discovery calls in new tests use synthetic records and mocks; no paid provider, network, or real media content was used.

- `python -m pytest -q tests/test_media_pipeline_concurrency.py`: original code produced two expected failures (overlapping discovery and cancellation leaving a processing item); fixed code passed.
- `python -m pytest -q tests/test_media_pipeline_concurrency.py tests/test_media_retry.py tests/test_media_processor.py`: 24 passed, 1 upstream Starlette deprecation warning.
- `python -m ruff check --select F,B app/worker/media_pipeline.py tests/test_media_pipeline_concurrency.py`: passed.
- `python -m ruff format --check tests/test_media_pipeline_concurrency.py`: passed.
- `git diff --check`: passed.
- Full Ruff lint across the legacy media files remains nonzero for existing `UP017` timezone aliases and SQLModel comparison `E711`/`E712` rules; those predate this change and are outside the bounded fix.

## Review and limits

The fix excludes concurrent tasks within one Python process. It does not coordinate separate worker processes or hosts, and neither a database claim nor a migration was added. Existing persisted `processing` items still gate a run until the 90-minute stale cutoff; cancellation during an active item now marks it failed for explicit API retry. Orchestrator review and PR publication remain next.

## Review follow-up

Root accepted two review findings and authorized the narrow subprocess lifecycle seams. Cancellation while ffmpeg converts audio, ffmpeg segments large audio, or whisper-cli transcribes now kills the child and awaits `communicate()` before propagating cancellation. A process that already exited is tolerated. The existing local-whisper timeout behavior still kills and reaps the child.

The run persists completed and failed counts after each item outcome. Cancellation of a second item therefore records the completed first item and failed canceled item (`items_processed=1`, `items_failed=1`) before the run is finalized as failed. Normal completed-run counts remain unchanged.

Follow-up verification with Python 3.11.16:

- `python -m pytest -q tests/test_media_pipeline_concurrency.py tests/test_media_retry.py tests/test_media_processor.py tests/test_transcription_service.py`: 36 passed, 2 warnings (Starlette deprecation and an existing AsyncMock unawaited-coroutine warning from the transcription tests).
- `python -m ruff check --select F,B app/worker/media_pipeline.py app/services/media_processor.py app/services/transcription_service.py tests/test_media_pipeline_concurrency.py tests/test_media_processor.py tests/test_transcription_service.py`: passed.
- `git diff --check`: passed.

All subprocesses, downloads, transcription, and feed discovery in new tests are fakes or synthetic fixtures. No provider or external network call was made. This follow-up remains single-process only and adds no schema changes.
