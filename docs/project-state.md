# Project state

Updated 2026-09-27. Audit baseline: `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`. Original execution base: `e6e62677fe4f5b8f516e226a48080008cafc04e0`. Remote main refreshed: `86d3efdaf2506c700b3613dfd0bd9425a05ee8ec`.

## Objective and authority

Complete the [reliability backlog](work-packages/backlog.md), integrate and verify its output, inspect every PR's review comments, fix actionable findings, and list all PRs. Every worker/reviewer uses **Sol (`gpt-6-sol`)**. Pushes and scoped/aggregate PRs are authorized. Remote merges, releases, deployments, production-content inspection and paid provider calls are not authorized. No recurring automation exists.

**All 29 approved reliability package outcomes and all currently known actionable review corrections are implemented, integrated and locally verified.** They are published through 45 scoped PRs (#74–118), plus [aggregate PR #119](https://github.com/LucaKaufmann/Ghostwriter/pull/119) against main; this checkpoint publishes the final native deletion corrections. Final hosted checks and newly arriving feedback still need inspection before milestone closeout.

Current aggregate source is `3c5eb75` with result documentation through `c7c859546d503d3c2af2c67c337f2b95dd6645f5`. The iOS tree matches verified worker `d4834bf` (source `cfb270c`); Android and shared trees match verified worker `62a3555` (source `c1a5386`). Both independent Sol reviews are clean. Final native gates: **225 Android tests, 195 iOS workspace tests, 58 shared tests with one intentional live skip, and both app builds**. Unaffected backend/browser/helper/live-contract gates remain valid below. Hosted checks at the earlier aggregate `0591f1f` passed 10 checks with one intentional image-publication skip; that result predates these final native corrections.

The [PR index](work-packages/results/PR-INDEX.md) lists all 46 PRs and immutable evidence; the [review ledger](work-packages/results/PR-REVIEW-FOLLOWUP.md) records accepted fixes and rejected/superseded findings. Fifteen PRs (#74–88) were externally merged; seven (#76/77/81/83/84/85/88) landed in prerequisite branches. Main contains #74/75/78/79/80/82/86/87. Thirty-one PRs remain open. Root has not merged remotely or deployed. The historical audit includes broader opportunities outside this reliability scope.

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
| Combined integration | Root; source accepted and locally verified | `integration`, branch `codex/backlog-integration`, source `3c5eb75`, result checkpoint `c7c8595`. Native source comparisons to verified worker trees passed. Publish and inspect final hosted checks/feedback. |
| iOS initial deletion and visibility | Sol iOS owner; accepted/integrated | Worker source `cfb270c`, docs head `d4834bf`; integrated `fc70077/6414dcd/c8f5008`, docs through `6cb80af`. Initial create/delete safely coalesces only unsent eligible prefixes; retained same-scope deletion survives conflict, acknowledgement, pull and explicit older-head resolution. 53 focused/195 workspace/App build; cumulative Sol review clean. Result: `AGGREGATE-IOS-INITIAL-DELETE.md`. |
| Android deletion visibility | Sol Android owner; accepted/integrated | Worker source `c1a5386`, docs head `62a3555`; integrated `3c5eb75/c7c8595`. Live server projection respects the latest retained intent in logical queue order; deleted feeds remain excluded from visible and local-generation queries. 35 focused/225 App/58 shared plus one intentional skip/APK; Sol review clean. Result: `AGGREGATE-ANDROID-DELETE-VISIBILITY.md`. |
| Earlier package/review work | Accepted/integrated/published | All prior fixes, schema upgrades, URL-generation guards, scheduling/retry recovery, backend ownership/publication, web conflict recovery and helper transport are recorded in immutable PR-index results and review dispositions. No implementation worker remains active. |
| Final review and continuity | Root; publication refresh pending | Every PR's paginated inline/review/issue comments inspected. Latest accepted hosted finding is #119/4116721613; its complete iOS fix also led to the reproduced Android parity correction. Update #106 and #119, inspect current publication comments/checks, then close the milestone. No external review replies. |

## Verification baseline

All checks use fixtures/synthetic sources and mocked external providers. Logs are in `/private/tmp/epilogue-backlog-20260927/`.

| Combined gate | Source / command or log | Verified result |
|---|---|---|
| Backend | f371a84; `python -m pytest -q`; final-backend-legacy-cap-combined.log | **451 passed**. |
| Live Ktor→FastAPI | f371a84; `python3 scripts/verify-feed-sync-contract.py --python /private/tmp/epilogue-runtime-312/bin/python`; final-live-legacy-cap-contract.log | **1 passed, no skips**, including native decoding of legacy caps. |
| Shared iOS/framework | d455f05; `:shared:iosSimulatorArm64Test :shared:assembleEpilogueSharedXCFramework --offline --no-daemon` |58passed; full debug/release XCFramework succeeded. Later shared changes only strengthen Android live-test fixture. |
| iOS |cfb270c, integrated c8f5008; `xcodebuildmcp simulator build/test`, schemes Epilogue/Epilogue-Workspace; aggregate-ios-initial-delete-{workspace-projection-final,app-build-projection-final}.log | App build passed;195/195 workspace unit tests, UI target excluded, iPhone16Plus/iOS18.6.53 focused sync tests and cumulative Sol review passed. Later Android-only source changes do not affect this gate. |
| Browser |06ec2e7; `npm run check`, `npm run test:e2e` with production build; final-web-baseline-closeout-{check,browser}.log |0errors/warnings;40browser tests and production build passed. |
| Live reading/listening | f371a84; `JOURNEY_PYTHON=/private/tmp/epilogue-runtime-312/bin/python npm run test:e2e -- --config=tests/e2e/reading-listening.playwright.config.ts`; final-web-baseline-closeout-journey.log | **1 passed**, real local API/SQLite/browser with synthetic sources and silentMP3. |
| Android | c1a5386, integrated 3c5eb75; `:app:testDebugUnitTest :shared:testDebugUnitTest :app:assembleDebug --offline --no-daemon`; android-delete-visibility-full.log | **225 App/58 shared passed**, one intentional live skip; debug APK. |
| Helper |5f3ce6d; `python3 -m unittest discover -s skills/ghostwriter-one-off-podcast/tests`; final-helper-transport.log |20passed on Python3.14.3; no real API/provider requests. |

Existing Swift concurrency/deprecation warnings, non-failing CoreData checksum messages, Pydantic advisory and historical AsyncMock warning remain. Historical `release_021.sql` whitespace is deliberately preserved; use `git diff --check origin/main..HEAD -- . ':!ghostwriter/tests/fixtures/release_021.sql'` rather than claiming an unqualified whitespace pass.

Runtime: Python3.11 fixture venv `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv` (bin first inPATH and site-packages before localGhostwriter inPYTHONPATH to avoid Alembic shadowing); requirements-onlyPython3.12 `/private/tmp/epilogue-runtime-312/bin/python`; JDK17 `/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`; both AndroidSDK variables `/private/tmp/epilogue-backlog-20260927/android-sdk`; Tuist4.152/Xcode26.5/xcodebuildmcp2.3/iOS18.6; Node24/npm11 locked dependencies.

No real-provider audio-quality, physical-device background timing, KOReader hardware, arm64-container-runtime, signing/distribution or production-restore claim. Generation gates are process-local. Android retry identity uses an isolated read-only internal WorkManager2.9 periodCount adapter: dependency upgrades must reverify its retry/ack lifecycle. Reads fail conservatively when identity is unavailable.

## Schema and branch coordination

Alembic026 feed versions/receipts,027 source acknowledgements,028 one-off ownership; Room9 feed outbox,10 delivery,11 scheduled coverage; frozen SwiftDataV1→V2 feed sync→V3 delivery. Root allocates revisions. No new revision for response projection or diagnosticsJSON mode.

Frozen comparison branches: `codex/review-fixes-verified-base`6f9a328; `codex/review-followup-base`ae0e8dd; `codex/ios-sync-review-verified-base`6e232cd. These are PR bases, not current main. Historical notes/results remain recoverable via immutable PR-index links; ignored `tasks/` can be rebuilt from this checkpoint.

## Exact next action

1. Publish this accepted native correction checkpoint to #106/#119, inspect final hosted checks and refresh all PR feedback. No implementation or local verification remains outstanding.
2. Record the exact hosted source revision and final review cutoff, then report the 29 completed packages and all 46 PRs. Aggregate #119 is the consolidated candidate for a separately authorized merge/release decision; do not merge every historical stacked PR. No remote merge or deployment is authorized.

Protected work: original `/Users/luca/git/Epilogue` stays maincdb776d with local audit/planning files. `/Users/luca/git/Epilogue-secondary` has staged CLAUDE.md, Android SettingsScreen.kt and deployment-example changes on gitbutler/workspace14a753e. Do not absorb/reset/publish them. Inspect other historical worktrees before reuse.
