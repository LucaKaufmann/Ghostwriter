# Project state

Updated 2026-09-27. Historical audit: `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`. Frozen original execution base: `e6e62677fe4f5b8f516e226a48080008cafc04e0`. Current remote main: `fb8279409a92a21b1df83cc6fa6298abe3271403` (refreshed during closeout).

## Objective and authority

Complete the [autonomous reliability backlog](work-packages/backlog.md), integrate and verify its output, inspect every PR review comment, fix actionable findings, and list all PRs. The user owns decisions through this orchestrator; every worker and independent reviewer uses **Sol (`gpt-6-sol`)**. Pushes and scoped/aggregate PR creation are authorized. Remote merges, releases, deployments, production-content inspection and paid provider calls are not authorized. No recurring automation is configured.

**All 29 original package outcomes are now published.** PR74–118 comprise 45 PRs including design, implementation stages and review follow-ups. This is publication progress, not final acceptance: The original combined Android gate passed. New hosted review findings in native forms, iOS scheduling and web pending state are under correction; final combined gates, aggregate publication and the last comment/CI sweep remain. See the [PR index](work-packages/results/PR-INDEX.md), [review disposition ledger](work-packages/results/PR-REVIEW-FOLLOWUP.md), and per-package `docs/work-packages/results/` files for historical evidence. The audit remains a dated snapshot.

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
| Combined integration | Root; final checks | `integration`, `codex/backlog-integration`, current71e2e86. All accepted original outcomes and fixes through118 are integrated. Recovery acceptance note is committeda88eacb. Preserve current V3 fixture when combining V2 feed tests. |
| Android scheduled coverage | Accepted / published | PR118 `efa1669`, `review-android-delivery`; accepted098be02 Sol clean, dependency merge preserved all coverage source/tests. Integrated71e2e86. Room11, bounded ingestion and anchored occurrence coverage. Combined191 App/58 shared passed plus1 intentional live skip/debug build. |
| Android feed review | Published; new correction active | PR112 `9f1d393`, `review-android-sync`; final173 App/shared59with1skip/build, Sol clean. Head-only correction, freshest acknowledged successor snapshot, unresolved local upserts after disabling sync, snapshot history clear. Integrated193a306/b5f406d. Separate V3 coordinator fixture9127a92 fixes prior iOS CI failure. New4116133533 stale untouched correction fields is assigned to Sol android_sync_closeout on the same PR112 branch. |
| Web conflict review | Published; new correction active | PR111 `7fe3504`, `review-web-conflicts`;36 browser/check/build, final Sol clean; both conflict screenshots inspected. Concurrent proposals, partial restore snapshot and form-session isolation. Integrated36951ca/389560b. New4116133843 restore pending state blocks unrelated Add; Sol config_sync_closeout owns a separate pending-state fix on PR111 branch. |
| iOS sync review | Published; new comment correction | PR115 `1913d9c`, `review-ios-sync`; focused37/App75, final Sol clean, rejected-delete UI evidence inspected. Integrated67027ac with current V3 test schema. New comment4116111625: delete-head resolution must replay later re-add visibility; Sol ios_sync_closeout owns the bounded correction. Frozen0cfba92 replay plus c526cb6 complete re-add payload now passes38 focused/79 App with actual KMP serialization and delete/re-add acknowledgements across reopen. Independent Sol review ofc526cb6 is running; not yet pushed/integrated. Historical full successor payloads remain untouched because copied versus intentional fields cannot safely be inferred. |
| iOS recovery | Published; new correction active | PR116 `c315662`, `ios-recovery`; accepted product21e3db8/tests5548865, integratedd455f05. Data59/Scheduler9 after correction; combined workspace169 now passes. Max2 automatic attempts per occurrence, shared gate, truthful BG outcomes, artifact work off MainActor. Final context-staleness finding did not reproduce; automatic claim release was rejected by confirmed policy and tested with actual empty retry/explicit regeneration. These are evidence-based dispositions, not a claim that final review emitted zero findings. New4116125704 captured Calendar.current is assigned to Sol ios_sync_closeout in ios-recovery after freezing115. |
| Backend review | Accepted / integrated | PR108 publication661637c;109 asyncDNS/syncf774ccfe;113 feedlimitsffd859b;114 durable one-off ownership028/b92e5b9. Combined444 tests pass. No further backend implementation pending. New helper download compatibility finding is assigned separately below. |
| Verification fixes | Accepted / published | PR110 `cd2f83e`, metadata isolation/live409 assertion/backup instructions plus verified V3 coordinator fixture. Old hosted iOS failure is on prior1878202; refresh current checks. |
| Helper download follow-up | Accepted / published | PR117 `304f964`, `review-helper-download`, baseae0e8dd. PR86 issuecomment5857583055 fixed: validated episode UUID downloads through configured API origin with credential/redirect guards retained. Branch Python3.11 tests20/Ruff; integrated Python3.14 tests20; independent Sol clean. Integrated5f3ce6d. |
| Review/CI sweep | Root; active | Paginated74–117 review bodies/inline/issue comments refreshed by Sol;149 current-head checks succeeded,24 skipped,0 failed/pending. New111/112/116 findings assigned above; PR106 contract inconsistencies corrected locally.117 has no findings and4 green checks. Refresh118 and changed heads/aggregate before closeout; no external replies posted. |
| Continuity | Root | Open PR106, branch `codex/project-continuity-followup`, worktree `project-continuity`; latest published0aae34b. Root checkpoint/ledger changes since then need copying and publishing. Original PR80 is externally merged. |

Eight PRs74–81 were merged externally. Main contains74/75/78/79/80;76/77/81 landed only in prerequisite branches. The orchestrator has not remotely merged. A final aggregate PR against refreshed main is required so the owner does not have to reconcile stacks.

## Verification baseline

All checks used fixtures/synthetic content and mocked external providers.

| Combined check | Revision / evidence | Result |
|---|---|---|
| Backend | 5aa43f3; `final-backend-combined.log` | **444 passed**, including fresh/upgrade migrations, ownership, publication failure/recovery and feed CAS. Later changes are native/web/helper only. |
| Live Ktor→FastAPI | 5aa43f3; `scripts/verify-feed-sync-contract.py --python /private/tmp/epilogue-runtime-312/bin/python` | **1 passed**, no skips, required409/status codes checked. |
| Shared iOS and framework | d455f05; `:shared:iosSimulatorArm64Test :shared:assembleEpilogueSharedXCFramework --offline --no-daemon` | **58 passed**, no failures/skips; full debug/release XCFramework succeeded. |
| iOS combined | d455f05; Tuist install/generate, xcodebuildmcp simulator build/test | App build passed; **169/169 workspace unit tests passed**, UI target excluded. V3 simulator3B168BD4. |
| Browser combined | 389560b; `npm run check`, `npm run test:e2e` | Check0 errors/warnings; production build and **36 browser tests passed**. |
| Live reading/listening | 389560b; `JOURNEY_PYTHON=/private/tmp/epilogue-runtime-312/bin/python npm run test:e2e -- --config=tests/e2e/reading-listening.playwright.config.ts` | **1 passed**, real local API/SQLite/browser with synthetic sources/providers and silentMP3. |
| Helper combined | 5f3ce6d; `python3 -m unittest discover -s skills/ghostwriter-one-off-podcast/tests` | **20 passed** on Python3.14.3; no real API/provider requests. |
| Android combined | 71e2e86; `:app:testDebugUnitTest :shared:testDebugUnitTest :app:assembleDebug --offline --no-daemon`; final-android-combined.log | **191 App passed;58 shared passed,1 intentional live skip; debug APK built.** Pending correction-form change requires affected verification afterward. |

Logs are under the worktree root's parent. Existing Swift concurrency/deprecation warnings, non-failing CoreData checksum diagnostics, Pydantic advisory and an intermittent historical AsyncMock warning remain. Captured `release_021.sql` preserves trailing whitespace from the historical SQL dump; aggregate whitespace check passes with that fixture excluded. No semantic fixture rewrite was made.

Runtime: Python3.11.16 fixture venv `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv`; put venv bin first in PATH and site-packages before current Ghostwriter in PYTHONPATH to avoid the local Alembic directory shadowing the installed CLI. Requirements-only Python3.12 is `/private/tmp/epilogue-runtime-312/bin/python`. JDK17 at `/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`; set ANDROID_HOME and ANDROID_SDK_ROOT to `/private/tmp/epilogue-backlog-20260927/android-sdk`. Tuist4.152, Xcode26.5, xcodebuildmcp2.3, simulator iOS18.6. Node24/npm11 with locked dependencies.

No real provider audio quality, KOReader hardware, physical-device background timing, signing/distribution, production restoration, or arm64 container runtime claim. Process-local generation gates are not distributed locks. A lost previously delivered EPUB requires explicit regeneration. Native durable config outbox and backend/native feature parity remain incomplete.

## Schema and branch coordination

Alembic026 feed versions/receipts,027 publication acknowledgements,028 durable one-off ownership are integrated and tested. Room9 feed outbox,10 delivery ledger,11 scheduled-run coverage (current sole owner above). SwiftDataV1 frozen legacy, V2 feed sync, V3 delivery. No independent revision allocation.

Frozen PR comparison branches remain immutable: `codex/review-fixes-verified-base`6f9a328, `codex/review-followup-base`ae0e8dd, `codex/ios-sync-review-verified-base`6e232cd. They are comparison points, not current main. Historical results and scope briefs remain in tracked docs; `tasks/` is ignored and may be rebuilt from this checkpoint.

## Exact next action

1. Complete newly refreshed PR111/112/115/116 corrections, review independently, publish updates and integrate. Android scheduled coverage118 is accepted.
2. Run final combined Android/shared/debug APK checks. Rerun affected combined iOS tests after accepting the current PR115 correction. Do not repeat unrelated passed gates.
3. Refresh all PR review comments/current-head CI, address actionable findings, and update the disposition ledger/index.
4. Publish the final aggregate PR against current main with the dependency map, verified results and limitations. Attach every created PR. Check the aggregate's review/checks before final acceptance.
5. Publish this compact checkpoint through PR106 and include it in the aggregate; report all PRs and remaining explicit limitations. The active goal is not complete yet.

Protected work: original `/Users/luca/git/Epilogue` stays main atcdb776d with local audit/planning files. `/Users/luca/git/Epilogue-secondary` has staged CLAUDE.md, Android SettingsScreen.kt and deployment-example changes on gitbutler/workspace at14a753e; do not absorb, reset or publish them. Other historical worktrees require inspection before reuse.
