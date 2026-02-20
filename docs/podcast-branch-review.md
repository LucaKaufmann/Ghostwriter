# Branch Review: `feature/podcast-digests`

**Date:** 2026-02-20
**Commits:** 28 (81b8f27..6cee4cc)
**Scope:** 5825 lines added across 26 files

## Migrations & Infrastructure: PASS

All 4 migrations (014-017) are idempotent, correctly chained, and match the model schemas exactly. Startup ordering, worker integration, cleanup jobs, and router registration are all correct.

Pre-existing issue: `MediaProcessingRun` is missing from `alembic/env.py` imports, which could cause future autogenerate runs to try dropping that table.

---

## Must Fix Before Merge

### 1. Blocking `subprocess.run` in async context
**Severity:** High
**Location:** `podcast_service.py:2090-2123`

`_run_subprocess` and `_probe_audio_duration_seconds` use synchronous `subprocess.run()` inside an `asyncio.Task`. This blocks the entire FastAPI event loop while ffmpeg stitches audio segments, making the server unresponsive for seconds.

**Fix:** Use `asyncio.create_subprocess_exec()` or `asyncio.to_thread()`.

### 2. No path traversal validation on file serving
**Severity:** High
**Location:** `podcast.py:559, 608, 736`

`stream_podcast_episode`, `download_podcast_episode`, and artwork serving read `audio_path`/`artwork_path` from the DB and serve via `FileResponse` without validating the path is within the expected output directory. If the DB is ever compromised, this enables arbitrary file reads.

**Fix:** Add `path.resolve().is_relative_to(expected_parent.resolve())` check before serving.

### 3. Race condition: duplicate episode creation crashes with unhandled IntegrityError
**Severity:** High
**Location:** `podcast_service.py:548-660`

`queue_episode_generation` does SELECT then INSERT without locking. Concurrent requests for the same digest both pass the existence check, one INSERT succeeds, the other crashes with a raw 500 `IntegrityError`.

**Fix:** Wrap in try/except `IntegrityError`, re-query and return existing episode.

### 4. `_schedule_episode_task` may fail from scheduler thread
**Severity:** High
**Location:** `podcast_service.py:774-782`

Uses `asyncio.create_task()` which requires a running event loop. If `maybe_auto_generate_for_digest()` is called from a synchronous scheduler thread, this raises `RuntimeError: no running event loop`.

**Fix:** Use `asyncio.run_coroutine_threadsafe(coro, loop)` with proper cross-thread handling.

### 5. File deleted before DB commit — inconsistent state on failure
**Severity:** Medium
**Location:** `podcast.py:527-537`

`delete_podcast_episode` calls `os.remove(audio_path)` before `session.commit()`. If the commit fails, the audio file is gone but the DB record still exists pointing to a missing file.

**Fix:** Delete the file after successful commit.

### 6. Error messages may leak API keys
**Severity:** Medium
**Location:** `podcast_service.py:931`

`episode.error_message = str(exc)[:500]` stores raw exception text which may include API keys from HTTP headers. This is returned in API responses via `PodcastEpisodeStatusRead`.

**Fix:** Sanitize error messages before storage (strip `sk-*`, `xi-*`, `Bearer` patterns).

### 7. No upload size limit on artwork
**Severity:** Medium
**Location:** `podcast.py:761`

`await file.read()` with no size check. A multi-GB upload causes OOM.

**Fix:** Check `len(data) > MAX_SIZE` immediately after read, or configure FastAPI's max request body.

---

## Should Fix Before Merge

### 8. HTTP client created per TTS segment — no connection reuse
**Location:** `podcast_service.py:1854, 1898`

A new `httpx.AsyncClient` is created for every segment (30-80 per episode). Each requires a full TLS handshake, adding 6-18 seconds of pure overhead.

**Fix:** Create one client per `generate_audio` call and pass it through.

### 9. N+1 query in feedback profile building
**Location:** `podcast_service.py:999-1027`

For each feedback row, individually queries `session.get(DigestArticle, feedback.article_id)`. With hundreds of feedback rows, this is extremely slow on SQLite.

**Fix:** Single JOIN query or batch with `IN` clause.

### 10. RSS episode numbering is unstable
**Location:** `podcast.py:664, 688`

Episodes are sorted newest-first and enumerated from 1. Every new episode renumbers all existing ones, confusing podcast apps that track listened episodes by number.

**Fix:** Store a stable episode number in the DB, or use total_count - index.

### 11. N+1 queries in RSS feed generation
**Location:** `podcast.py:670`

`_resolve_episode_articles` runs per-episode for up to 100 episodes, producing 100 extra DB queries per feed request.

### 12. Incomplete podcast episodes silently marked as "ready"
**Location:** `podcast_service.py:1796`

Failed TTS segments return `b""` and are silently skipped. If many segments fail, the episode is marked "ready" with missing dialogue. Only if ALL segments fail does it error.

**Fix:** Track failure count and either fail the episode or warn the user if >N segments failed.

### 13. Delete during active generation orphans audio files
**Location:** `podcast.py:518-538`

No check for `generating_script`/`generating_audio` status before deletion. The background task continues, writes audio, but the DB record is gone. Audio files accumulate on disk.

**Fix:** Check status before deletion, or mark as "cancelled" and let the background task clean up.

### 14. Null safety on `article.content`
**Location:** `podcast_service.py:1047, 1067`

`article.content[:800]` and `article.content[:1000]` crash with `TypeError` if content is `None` (possible in old data).

**Fix:** `(article.content or "")[:800]`.

### 15. Debug prompt files never cleaned up
**Location:** `podcast_service.py:1100-1106, 1607-1610`

Script and TTS prompt debug files are written to `logs/podcast_*_prompts/` and never deleted. These accumulate indefinitely.

---

## Frontend Bugs

### 16. Shared mutation causes false loading spinners across settings sections
**Location:** `SettingsPage.svelte:1043+`

`updateClientConfigMutation` is shared between PDF, cover, and whisper settings. Saving one section makes all others show spinners.

### 17. Podcast mutation `onSuccess` resets all fields, potentially overwriting unsaved edits
**Location:** `SettingsPage.svelte:313-332`

`updatePodcastPreferencesMutation` is shared between generation and feed settings. Saving generation settings overwrites `podcastFeedEnabled` and `podcastFeedBaseUrl` with server values, reverting any unsaved feed changes.

### 18. Delete dialog silently does nothing for digests without a filename
**Location:** `DigestsPage.svelte:1185`

If `digest.filename` is falsy, clicking Delete closes the dialog but takes no action and shows no feedback.

---

## UX/UI Improvements (Nice to Have)

| # | Issue | Location | Suggestion |
|---|-------|----------|------------|
| 19 | Actions column too cluttered | `DigestsPage:843-921` | 5+ buttons in 320px — group or use overflow menu |
| 20 | Podcast error only shown on mobile | `DigestsPage:884 vs 1001` | Desktop omits error message that mobile shows |
| 21 | Podcast action template duplicated 3x | `DigestsPage` | Desktop, mobile, and covers views repeat the same UI logic |
| 22 | Schedule time shown for "manual" | `SettingsPage:1327` | Time input is irrelevant when schedule is manual |
| 23 | Podcast Generation card very long | `SettingsPage:1273-1566` | No visual separation between scheduling and TTS config |
| 24 | Feed URL shown when feed is disabled | `SettingsPage:1625-1648` | Confusing — grey out or hide when disabled |
| 25 | Feed title/description not editable | `SettingsPage` | Fields exist in the API but have no form inputs |
| 26 | Mixed `<select>` vs Bits UI `Select.Root` | `SettingsPage` | Visual inconsistency between native and styled dropdowns |
| 27 | Cover images loaded sequentially | `DigestsPage:183-210` | Use `Promise.allSettled` for parallel loading |
| 28 | `status` typed as bare `string` | `types.ts:603` | Should be a union type for compile-time safety |
| 29 | No voice ID validation for ElevenLabs | `SettingsPage:1521` | Users can paste names instead of IDs with no feedback |

---

## Security Summary

| Severity | Finding |
|----------|---------|
| High | Path traversal on file serving — no directory validation (#2) |
| Medium | Feed token in querystring URLs — logged by proxies, visible in clients |
| Medium | API keys stored unencrypted in SQLite (#5 in security analysis) |
| Medium | Error messages may leak API keys in responses (#6) |
| Medium | No artwork upload size limit (#7) |
| Medium | LLM prompt injection via article content (XML-tag spoofing) |
| Medium | Missing security test coverage (no tests for invalid tokens, path traversal, auth failures) |
| Low | Server filesystem paths exposed in API responses |
| Low | No rate limiting on generation triggers (financial risk) |
| Low | Debug prompt files accumulate indefinitely (#15) |

---

## Verdict

The feature is architecturally sound — migrations are correct, worker integration is clean, and the polling/status system is well-designed with proper cancellation tokens and backoff. The podcast generation pipeline (chunked script generation, segment-based TTS, ffmpeg stitching) is solid in design.

**Must fix (7 items):** The blocking subprocess calls (#1), path traversal (#2), race condition (#3), and async task scheduling (#4) are the most serious — they can crash the server or create security holes. Items #5-7 are straightforward fixes.

**Should fix (8 items):** Performance issues (#8, #9, #11), the unstable episode numbering (#10), and silent failures (#12) will cause real user-facing problems as usage grows.

**Frontend bugs (3 items):** The shared mutation issue (#17) is the most impactful — it can silently overwrite user settings.
