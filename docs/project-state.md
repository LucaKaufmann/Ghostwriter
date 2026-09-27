# Project state

Updated 2026-09-27. Historical audit: `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`. Frozen original execution base: `e6e62677fe4f5b8f516e226a48080008cafc04e0`. Current remote main: `fb8279409a92a21b1df83cc6fa6298abe3271403` (refreshed during closeout).

## Objective and authority

Complete the [autonomous reliability backlog](work-packages/backlog.md), integrate and verify its output, inspect every PR review comment, fix actionable findings, and list all PRs. The user owns decisions through this orchestrator; every worker and independent reviewer uses **Sol (`gpt-6-sol`)**. Pushes and scoped/aggregate PR creation are authorized. Remote merges, releases, deployments, production-content inspection and paid provider calls are not authorized. No recurring automation is configured.

**All 29 original package outcomes are now published.** PR74–116 comprise 43 PRs including design, implementation stages and review follow-ups. This is publication progress, not final acceptance: Android schedule migration, final combined Android verification, aggregate publication and the last comment/CI sweep remain. See the [PR index](work-packages/results/PR-INDEX.md), [review disposition ledger](work-packages/results/PR-REVIEW-FOLLOWUP.md), and per-package `docs/work-packages/results/` files for historical evidence. The audit remains a dated snapshot.

## Confirmed decisions

- Concurrent feed edits preserve the newer server version and retain the conflicting local proposal for explicit resolution.
- Normal native editions deliver an article once even after history or EPUB deletion. Explicit regeneration may repeat articles. Recovery preserves existing delivery claims and does not silently regenerate a lost artifact.
- A podcast reference prevents manual digest deletion and causes scheduled deletion to skip it. Unrelated historical orphan files remain untouched.
- Feeds/config/digests remain largely installation-wide; podcast ownership is more granular. No multi-tenant isolation or native feature-parity claim was added.

Audience, platform/release priority, generated-podcast native UI, distributed scheduling and personal deployment helper DEPLOY-01 remain outside this reliability scope. Preserve offline behavior and existing enabled feature-flag configurations.

## Current task ledger

Worktree root: `/private/tmp/epilogue-backlog-20260927/`. Planning documents have one owner: root. Worker handles must be rechecked after interruption; an old branch or result note is not proof of active work or integration.

| Task | Owner / status | Location, output and next action |
|---|---|---|
| Combined integration | Root; final checks | `integration`, `codex/backlog-integration`, current389560b. All accepted original outcomes and fixes through116 are integrated; latest Android scheduled coverage is pending. Recovery acceptance note is intentionally unstaged. Preserve current V3 fixture when combining V2 feed tests. |
| Android scheduled coverage | Sol android_sync_closeout; correcting | `review-android-delivery`, `codex/review-android-delivery`, last frozen7fd02d9. Room11 scheduled trigger/period/occurrence/workId, bounded parallel feed ingestion, first-nonblank filtering and neutral partial copy. Review found legacy schedule cancellation could discard pending work. Owner is replacing the unshipped rename/cancel approach with WorkManager2.9 UPDATE using actual next scheduled time, off-main observation and disable guards. Preserve existing retry budget; tests/review/publication required. |
| Android feed review | Accepted / published | PR112 `9f1d393`, `review-android-sync`; final173 App/shared59with1skip/build, Sol clean. Head-only correction, freshest acknowledged successor snapshot, unresolved local upserts after disabling sync, snapshot history clear. Integrated193a306/b5f406d. Separate V3 coordinator fixture9127a92 fixes prior iOS CI failure. |
| Web conflict review | Accepted / published | PR111 `7fe3504`, `review-web-conflicts`;36 browser/check/build, final Sol clean; both conflict screenshots inspected. Concurrent proposals, partial restore snapshot and form-session isolation. Integrated36951ca/389560b. |
| iOS sync review | Published; new comment correction | PR115 `1913d9c`, `review-ios-sync`; focused37/App75, final Sol clean, rejected-delete UI evidence inspected. Integrated67027ac with current V3 test schema. New comment4116111625: delete-head resolution must replay later re-add visibility; Sol ios_sync_closeout owns the bounded correction. Historical full successor payloads remain untouched because copied versus intentional fields cannot safely be inferred. |
| iOS recovery | Accepted / published | PR116 `c315662`, `ios-recovery`; accepted product21e3db8/tests5548865, integratedd455f05. Data59/Scheduler9 after correction; combined workspace169 now passes. Max2 automatic attempts per occurrence, shared gate, truthful BG outcomes, artifact work off MainActor. Final context-staleness finding did not reproduce; automatic claim release was rejected by confirmed policy and tested with actual empty retry/explicit regeneration. These are evidence-based dispositions, not a claim that final review emitted zero findings. |
| Backend review | Accepted / integrated | PR108 publication661637c;109 asyncDNS/syncf774ccfe;113 feedlimitsffd859b;114 durable one-off ownership028/b92e5b9. Combined444 tests pass. No further backend implementation pending. New helper download compatibility finding is assigned separately below. |
| Verification fixes | Accepted / published | PR110 `cd2f83e`, metadata isolation/live409 assertion/backup instructions plus verified V3 coordinator fixture. Old hosted iOS failure is on prior1878202; refresh current checks. |
| Helper download follow-up | Sol config_sync_closeout; implementing | `review-helper-download`, `codex/review-helper-download`, baseae0e8dd. PR86 issuecomment5857583055: internal API address/public advertised URL mismatch. Download known episode endpoint through configured API origin, retain credential/redirect guards, transport fixtures and independent review before new PR. |
| Review/CI sweep | Root; active | Paginated74–116 snapshot in temporary `pr-feedback`; tracked dispositions in review ledger. Latest new findings115/86 assigned above. Current86/110checks passed;111/112/115/116pending with no failures in the snapshot. Refresh the future Android follow-up and aggregate PR after creation. No external review replies posted. |
| Continuity | Root | Open PR106, branch `codex/project-continuity-followup`, worktree `project-continuity`; latest published1f52bdf. Root checkpoint/ledger changes since then need copying and publishing. Original PR80 is externally merged. |

Eight PRs74–81 were merged externally. Main contains74/75/78/79/80;76/77/81 landed only in prerequisite branches. The orchestrator has not remotely merged. A final aggregate PR against refreshed main is required so the owner does not have to reconcile stacks.

## Verification baseline

All checks used fixtures/synthetic content and mocked external providers.

| Combined check | Revision / evidence | Result |
|---|---|---|
| Backend | 5aa43f3; `final-backend-combined.log` | **444 passed**, including fresh/upgrade migrations, ownership, publication failure/recovery and feed CAS. Later changes are native/web only. |
| Live Ktor→FastAPI | 5aa43f3; `scripts/verify-feed-sync-contract.py --python /private/tmp/epilogue-runtime-312/bin/python` | **1 passed**, no skips, required409/status codes checked. |
| Shared iOS and framework | d455f05; `:shared:iosSimulatorArm64Test :shared:assembleEpilogueSharedXCFramework --offline --no-daemon` | **58 passed**, no failures/skips; full debug/release XCFramework succeeded. |
| iOS combined | d455f05; Tuist install/generate, xcodebuildmcp simulator build/test | App build passed; **169/169 workspace unit tests passed**, UI target excluded. V3 simulator3B168BD4. |
| Browser combined | 389560b; `npm run check`, `npm run test:e2e` | Check0 errors/warnings; production build and **36 browser tests passed**. |
| Live reading/listening | 389560b; `JOURNEY_PYTHON=/private/tmp/epilogue-runtime-312/bin/python npm run test:e2e -- --config=tests/e2e/reading-listening.playwright.config.ts` | **1 passed**, real local API/SQLite/browser with synthetic sources/providers and silentMP3. |
| Android combined | Final run pending Android coverage correction | Branch PR112173/shared59with1skip/build passed; earlier combined157/shared57with1skip/build is historical, not the final gate. |

Logs are under the worktree root's parent. Existing Swift concurrency/deprecation warnings, non-failing CoreData checksum diagnostics, Pydantic advisory and an intermittent historical AsyncMock warning remain. Captured `release_021.sql` preserves trailing whitespace from the historical SQL dump; aggregate whitespace check passes with that fixture excluded. No semantic fixture rewrite was made.

Runtime: Python3.11.16 fixture venv `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv`; put venv bin first in PATH and site-packages before current Ghostwriter in PYTHONPATH to avoid the local Alembic directory shadowing the installed CLI. Requirements-only Python3.12 is `/private/tmp/epilogue-runtime-312/bin/python`. JDK17 at `/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`; set ANDROID_HOME and ANDROID_SDK_ROOT to `/private/tmp/epilogue-backlog-20260927/android-sdk`. Tuist4.152, Xcode26.5, xcodebuildmcp2.3, simulator iOS18.6. Node24/npm11 with locked dependencies.

No real provider audio quality, KOReader hardware, physical-device background timing, signing/distribution, production restoration, or arm64 container runtime claim. Process-local generation gates are not distributed locks. A lost previously delivered EPUB requires explicit regeneration. Native durable config outbox and backend/native feature parity remain incomplete.

## Schema and branch coordination

Alembic026 feed versions/receipts,027 publication acknowledgements,028 durable one-off ownership are integrated and tested. Room9 feed outbox,10 delivery ledger,11 scheduled-run coverage (current sole owner above). SwiftDataV1 frozen legacy, V2 feed sync, V3 delivery. No independent revision allocation.

Frozen PR comparison branches remain immutable: `codex/review-fixes-verified-base`6f9a328, `codex/review-followup-base`ae0e8dd, `codex/ios-sync-review-verified-base`6e232cd. They are comparison points, not current main. Historical results and scope briefs remain in tracked docs; `tasks/` is ignored and may be rebuilt from this checkpoint.

## Exact next action

1. Accept the Android schedule migration correction only after real behavioral tests and independent Sol review; publish its scoped PR and integrate it.
2. Run final combined Android/shared/debug APK checks. Do not repeat already-passed backend/iOS gates unless relevant source changes.
3. Refresh all PR review comments/current-head CI, address actionable findings, and update the disposition ledger/index.
4. Publish the final aggregate PR against current main with the dependency map, verified results and limitations. Attach every created PR. Check the aggregate's review/checks before final acceptance.
5. Publish this compact checkpoint through PR106 and include it in the aggregate; report all PRs and remaining explicit limitations. The active goal is not complete yet.

Protected work: original `/Users/luca/git/Epilogue` stays main atcdb776d with local audit/planning files. `/Users/luca/git/Epilogue-secondary` has staged CLAUDE.md, Android SettingsScreen.kt and deployment-example changes on gitbutler/workspace at14a753e; do not absorb, reset or publish them. Other historical worktrees require inspection before reuse.
