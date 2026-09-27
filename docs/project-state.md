# Project state

Updated 2026-09-27. Audit baseline: `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`. Original execution base: `e6e62677fe4f5b8f516e226a48080008cafc04e0`. Remote main refreshed: `86d3efdaf2506c700b3613dfd0bd9425a05ee8ec`.

## Objective and authority

Complete the [reliability backlog](work-packages/backlog.md), integrate and verify its output, inspect every PR's review comments, fix actionable findings, and list all PRs. Every worker/reviewer uses **Sol (`gpt-6-sol`)**. Pushes and scoped/aggregate PRs are authorized. Remote merges, releases, deployments, production-content inspection and paid provider calls are not authorized. No recurring automation exists.

**All 29 approved reliability package outcomes are implemented and published.** The last four review findings are corrected locally: bound full-pull documentation, immutable-URL metadata edits during DNS failure, legacy cap consumption, and new-feed URL admission. The backend, Android/shared and iOS component gates plus combined integration checks passed. Independent Sol reviews are clean on the final component changes, including the iOS change in the combined source context. Publication/hosted-feedback checks remain required before closeout. Previously published aggregate #119 at `0987f80` passed10 hosted checks with one intentional publication skip.

The [46-PR index](work-packages/results/PR-INDEX.md) and [review ledger](work-packages/results/PR-REVIEW-FOLLOWUP.md) preserve evidence. At2026-09-27T21:16Z,15PRs were externally merged (seven into prerequisites),31remain open. All109inline comments,57review bodies and47issue comments were inspected; no additional findings appeared in that refresh. No orchestrator merge or deployment. Broader product/release items remain outside this reliability milestone.

## Confirmed product decisions

- Newer server feed state wins conflicts; the device retains its local proposal for explicit resolution.
- Normal native editions deliver once across history/EPUB deletion; explicit regeneration can repeat content. Recovery preserves delivery claims and never silently regenerates a lost artifact.
- Podcast references block manual digest deletion and skip scheduled deletion. Unknown historical orphan files remain untouched.
- Feeds/configuration/digests are largely installation-wide; podcast ownership is more granular. No tenant isolation or full native feature-parity claim.

Audience/release priority, generated-podcast native UI, durable native configuration outbox, distributed scheduling and personal deployment helper DEPLOY-01 remain outside this reliability scope. Preserve offline reading and already-enabled feature-flagged configurations.

## Task ledger

Worktrees: `/private/tmp/epilogue-backlog-20260927/`. Root alone owns shared planning/contract documents. Recheck actual commits after interruption; an old status is not proof of integration.

| Task | Owner / state | Output and next action |
|---|---|---|
| Combined integration | Root; local checks passed | `integration`, branch `codex/backlog-integration`, product source `37d43a0`, evidence through `df4382b`. Exact component source comparisons to verified worker trees passed. Real Ktor/API and reading/listening journey each1passed. All local acceptance gates and final Sol reviews passed; publication/hosted checks remain. |
| Backend feed compatibility | Sol config_sync_closeout; accepted/integrated | Worker source `ec8ed10`, docs `b0c9e5f`, integrated through `df4382b`. Metadata PUT retains CAS without DNS on immutable URL; bindery projects raw legacy caps; genuinely new URL admission rejects malformed ports.462backend, focused failure/concurrency fixtures, clean cumulative Sol review. `AGGREGATE-BACKEND-FEED-COMPAT.md`. |
| Shared/Android feed URL admission | Sol android_sync_closeout; accepted/integrated | Worker source `c63ded1`, docs `863dc2a`, integrated `8a4f27c/a635667`. New-only syntax guard preserves exact keys and legacy wire/snapshot/edit compatibility.229App/59shared+1intentional skip/APK, clean Sol review. `AGGREGATE-FEED-URL-ADMISSION.md`. |
| iOS feed URL admission | Sol ios_sync_closeout; accepted/integrated | Worker `470e834`, integrated `37d43a0`, consumes shared `c63ded1`.55focused/197workspace/App build;59shared native tests and debug/releaseXCFramework passed. Integrated-source Sol review5148 is clean. The earlier isolated review saw already-implemented source dependencies; actual compiled framework and combined source establish those dependencies. |
| Earlier package/review work | Accepted/integrated/published | All prior fixes and native deletion invariants are preserved. iOS initial deletion source `cfb270c`/Android deletion visibility `c1a5386` remain included and covered by the newer native full gates. Immutable PR-index results and review dispositions retain history. |
| Final review and continuity | Root; four new findings corrected, publication pending | Root owns bound-full-pull handoff fix, shared contracts and state. Publish106/119 with final verification evidence, inspect hosted checks/comments, close the milestone. No external review replies. |

## Verification baseline

All checks use fixtures/synthetic sources and mocked external providers. Logs are in `/private/tmp/epilogue-backlog-20260927/`.

| Combined gate | Source / command or log | Verified result |
|---|---|---|
| Backend | ec8ed10; `python -m pytest -q`; aggregate-backend-feed-compat-final-full.log | **462 passed**. |
| Live Ktor→FastAPI | 37d43a0; `python3 scripts/verify-feed-sync-contract.py --python /private/tmp/epilogue-runtime-312/bin/python`; final-feed-admission-live-contract.log | **1 passed, no skips**, including native decoding of legacy caps. |
| Shared iOS/framework | c63ded1; `:shared:iosSimulatorArm64Test :shared:assembleEpilogueSharedXCFramework --offline --no-daemon` |59passed; full debug/release XCFramework succeeded, Swift export verified. |
| iOS |470e834 +shared c63ded1, integrated37d43a0; `xcodebuildmcp simulator build/test`, schemes Epilogue/Epilogue-Workspace; aggregate-ios-feed-url-admission-{focused,workspace-test,app-build}.log | App build passed;197/197 workspace unit tests, UI target excluded, iPhone16Plus/iOS18.6.55focused sync tests passed. |
| Browser |06ec2e7; `npm run check`, `npm run test:e2e` with production build; final-web-baseline-closeout-{check,browser}.log |0errors/warnings;40browser tests and production build passed. |
| Live reading/listening | 37d43a0; `JOURNEY_PYTHON=/private/tmp/epilogue-runtime-312/bin/python npm run test:e2e -- --config=tests/e2e/reading-listening.playwright.config.ts`; final-feed-admission-journey.log | **1 passed**, real local API/SQLite/browser with synthetic sources and silentMP3. |
| Android |c63ded1, integrated8a4f27c; `:app:testDebugUnitTest :shared:testDebugUnitTest :app:assembleDebug --offline --no-daemon`; feed-url-full.log |229App/59shared passed, one intentional live skip; debug APK. |
| Helper |5f3ce6d; `python3 -m unittest discover -s skills/ghostwriter-one-off-podcast/tests`; final-helper-transport.log |20passed on Python3.14.3; no real API/provider requests. |

Existing Swift concurrency/deprecation warnings, non-failing CoreData checksum messages, Pydantic advisory and historical AsyncMock warning remain. Historical `release_021.sql` whitespace is deliberately preserved; use `git diff --check origin/main..HEAD -- . ':!ghostwriter/tests/fixtures/release_021.sql'` rather than claiming an unqualified whitespace pass.

Runtime: Python3.11 fixture venv `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv` (bin first inPATH and site-packages before localGhostwriter inPYTHONPATH to avoid Alembic shadowing); requirements-onlyPython3.12 `/private/tmp/epilogue-runtime-312/bin/python`; JDK17 `/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`; both AndroidSDK variables `/private/tmp/epilogue-backlog-20260927/android-sdk`; Tuist4.152/Xcode26.5/xcodebuildmcp2.3/iOS18.6; Node24/npm11 locked dependencies.

No real-provider audio-quality, physical-device background timing, KOReader hardware, arm64-container-runtime, signing/distribution or production-restore claim. Generation gates are process-local. Android retry identity uses an isolated read-only internal WorkManager2.9 periodCount adapter: dependency upgrades must reverify its retry/ack lifecycle. Reads fail conservatively when identity is unavailable.

## Schema and branch coordination

Alembic026 feed versions/receipts,027 source acknowledgements,028 one-off ownership; Room9 feed outbox,10 delivery,11 scheduled coverage; frozen SwiftDataV1→V2 feed sync→V3 delivery. Root allocates revisions. No new revision for response projection or diagnosticsJSON mode.

Frozen comparison branches: `codex/review-fixes-verified-base`6f9a328; `codex/review-followup-base`ae0e8dd; `codex/ios-sync-review-verified-base`6e232cd. These are PR bases, not current main. Historical notes/results remain recoverable via immutable PR-index links; ignored `tasks/` can be rebuilt from this checkpoint.

## Exact next action

1. Publish the final accepted source/evidence checkpoint. Component source trees match accepted/tested worker versions; no repeated local gate is needed unless source changes.
2. Publish106/119, refresh hosted checks and available feedback, then close the milestone and report all46PRs. No remote merge or deployment is authorized.

Protected work: original `/Users/luca/git/Epilogue` stays maincdb776d with local audit/planning files. `/Users/luca/git/Epilogue-secondary` has staged CLAUDE.md, Android SettingsScreen.kt and deployment-example changes on gitbutler/workspace14a753e. Do not absorb/reset/publish them. Inspect other historical worktrees before reuse.
