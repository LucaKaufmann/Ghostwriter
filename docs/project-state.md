# Project state

Updated 2026-09-27. Audit baseline: `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`. Original execution base: `e6e62677fe4f5b8f516e226a48080008cafc04e0`. Remote main refreshed: `86d3efdaf2506c700b3613dfd0bd9425a05ee8ec`.

## Objective and authority

Complete the [reliability backlog](work-packages/backlog.md), integrate and verify its output, inspect every PR's review comments, fix actionable findings, and list all PRs. Every worker/reviewer uses **Sol (`gpt-6-sol`)**. Pushes and scoped/aggregate PRs are authorized. Remote merges, releases, deployments, production-content inspection and paid provider calls are not authorized. No recurring automation exists.

**All 29 original package outcomes are published**, in45 scoped PRs (#74–118), plus [aggregate PR119](https://github.com/LucaKaufmann/Ghostwriter/pull/119) against main. All combined local acceptance gates passed. Final closeout awaits the aggregate review/comment/CI sweep; every local combined acceptance gate passed. The audit is historical; [PR index](work-packages/results/PR-INDEX.md) and [review dispositions](work-packages/results/PR-REVIEW-FOLLOWUP.md) link immutable evidence. Fifteen PRs74–88 were externally merged;76/77/81/83/84/85/88 landed in prerequisite branches. Main contains74/75/78/79/80/82/86/87. Root has not remotely merged anything.

## Confirmed product decisions

- Newer server feed state wins conflicts; the device retains its local proposal for explicit resolution.
- Normal native editions deliver once across history/EPUB deletion; explicit regeneration can repeat content. Recovery preserves delivery claims and never silently regenerates a lost artifact.
- Podcast references block manual digest deletion and skip scheduled deletion. Unknown historical orphan files remain untouched.
- Feeds/configuration/digests are largely installation-wide; podcast ownership is more granular. No tenant isolation or full native feature-parity claim.

Audience/release priority, generated-podcast native UI, durable native configuration outbox, distributed scheduling and personal deployment helper DEPLOY-01 remain outside this reliability scope. Preserve offline reading and already-enabled feature-flagged configurations.

## Active ledger

Worktrees: `/private/tmp/epilogue-backlog-20260927/`. Root alone owns shared planning/contract documents. Recheck workers and actual commits after interruption; old status is not proof of integration.

| Task | Owner / state | Exact next action and location |
|---|---|---|
| Combined integration | Root; final verification | `integration`, branch `codex/backlog-integration`, code d34e89a, published checkpointcfa81a3, aggregate PR119. All accepted original outcomes and follow-ups through web111acf7abc/iOS116879f237/backend1137871e7a integrated. Android11843581ef is integrated and the final combined gate passed. |
| Android scheduling/retry | Accepted/published/combined verified | `review-android-delivery`, PR11843581ef; c763ae9 product fix independently reviewed, actual WorkerWrapper lifecycle test43581ef passed. Integrated d34e89a; combined204 App/58shared passed+1intentional skip/debugAPK. |
| iOS recovery | Accepted/published/combined verified | `ios-recovery`, PR116879f237. Explicit optional mode in existing diagnosticsJSON distinguishes regeneration from normal/legacy recovery; unknown mode preserves other diagnostics. Data64 branch; combined176workspace tests/Appbuild passed at9464a65. No schema change. |
| Web conflict recovery | Accepted/published/combined verified | `review-web-conflicts`, PR111acf7abc. Newer typing survives late409/200; successful response advances only retained draft baseline. Combined40browser/productionbuild/check0/0 passed06ec2e7; final live journey1passed with backendf371a84. |
| Backend legacy caps | Accepted/published/combined verified | `review-feed-limits`, PR1137871e7a. Legacy read projection preserves raw rows/receipts. Sol clean; integratedf371a84; combined451backend and real Ktor/FastAPI fixture1passed, no skips. |
| Earlier accepted fixes | Integrated and published | PR11225e2b1d Android correction defaults survive pre-submit sync; PR115c526cb6 iOS delete/re-add serializes full successor; PR108/109/114 backend publication/DNS/ownership; PR117304f964 helper API-origin download. See immutable results/dispositions for individual evidence. |
| Review and CI sweep | Root; final pass pending | Full paginated74–118 inline/review-body/issue sweep found the above corrections plus PR106 documentation updates. Latest full45-PR sweep found no new feedback; exact-head CI149success/24skipped/4running/0failed. Running jobs are113iOS,116iOS,118Android+iOS; absent rollups are not passes. Refresh changed heads and aggregate. No external replies posted. |
| Continuity | Root; latest changes local | `project-continuity`, PR106 checkpoint7c426bf published. This checkpoint records aggregate119; refresh final review/CI dispositions before closeout. Do not overwrite implementation result files. |

## Verification baseline

All checks use fixtures/synthetic sources and mocked external providers. Logs are in `/private/tmp/epilogue-backlog-20260927/`.

| Combined gate | Source / command or log | Verified result |
|---|---|---|
| Backend | f371a84; `python -m pytest -q`; final-backend-legacy-cap-combined.log | **451 passed**. |
| Live Ktor→FastAPI | f371a84; `python3 scripts/verify-feed-sync-contract.py --python /private/tmp/epilogue-runtime-312/bin/python`; final-live-legacy-cap-contract.log | **1 passed, no skips**, including native decoding of legacy caps. |
| Shared iOS/framework | d455f05; `:shared:iosSimulatorArm64Test :shared:assembleEpilogueSharedXCFramework --offline --no-daemon` |58passed; full debug/release XCFramework succeeded. Later shared changes only strengthen Android live-test fixture. |
| iOS |9464a65; Tuist/xcodebuildmcp simulator build/test; final-ios-recovery-mode-{app-build,workspace-test}.log | App build passed;176/176workspace unit tests, UI target excluded, V3sim3B168BD4. No later iOS source changes. |
| Browser |06ec2e7; `npm run check`, `npm run test:e2e` with production build; final-web-baseline-closeout-{check,browser}.log |0errors/warnings;40browser tests and production build passed. |
| Live reading/listening | f371a84; `JOURNEY_PYTHON=/private/tmp/epilogue-runtime-312/bin/python npm run test:e2e -- --config=tests/e2e/reading-listening.playwright.config.ts`; final-web-baseline-closeout-journey.log | **1 passed**, real local API/SQLite/browser with synthetic sources and silentMP3. |
| Android | d34e89a; `:app:testDebugUnitTest :shared:testDebugUnitTest :app:assembleDebug --offline --no-daemon`; final-android-pr118-acceptance.log | **204 App/58 shared passed**,1intentional live skip; debug APK. |
| Helper |5f3ce6d; `python3 -m unittest discover -s skills/ghostwriter-one-off-podcast/tests`; final-helper-transport.log |20passed on Python3.14.3; no real API/provider requests. |

Existing Swift concurrency/deprecation warnings, non-failing CoreData checksum messages, Pydantic advisory and historical AsyncMock warning remain. Historical `release_021.sql` whitespace is deliberately preserved; use `git diff --check origin/main..HEAD -- . ':!ghostwriter/tests/fixtures/release_021.sql'` rather than claiming an unqualified whitespace pass.

Runtime: Python3.11 fixture venv `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv` (bin first inPATH and site-packages before localGhostwriter inPYTHONPATH to avoid Alembic shadowing); requirements-onlyPython3.12 `/private/tmp/epilogue-runtime-312/bin/python`; JDK17 `/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`; both AndroidSDK variables `/private/tmp/epilogue-backlog-20260927/android-sdk`; Tuist4.152/Xcode26.5/xcodebuildmcp2.3/iOS18.6; Node24/npm11 locked dependencies.

No real-provider audio-quality, physical-device background timing, KOReader hardware, arm64-container-runtime, signing/distribution or production-restore claim. Generation gates are process-local. Android retry identity uses an isolated read-only internal WorkManager2.9 periodCount adapter: dependency upgrades must reverify its retry/ack lifecycle. Reads fail conservatively when identity is unavailable.

## Schema and branch coordination

Alembic026 feed versions/receipts,027 source acknowledgements,028 one-off ownership; Room9 feed outbox,10 delivery,11 scheduled coverage; frozen SwiftDataV1→V2 feed sync→V3 delivery. Root allocates revisions. No new revision for response projection or diagnosticsJSON mode.

Frozen comparison branches: `codex/review-fixes-verified-base`6f9a328; `codex/review-followup-base`ae0e8dd; `codex/ios-sync-review-verified-base`6e232cd. These are PR bases, not current main. Historical notes/results remain recoverable via immutable PR-index links; ignored `tasks/` can be rebuilt from this checkpoint.

## Exact next action

1. Inspect aggregate119 and changed106/113/116/118 review bodies, inline/issue comments and current-head CI. Final full scoped sweep found no new feedback; address any new real findings.
2. Record final review/CI dispositions and report all46 PRs. All local combined gates passed; repeat only for relevant source changes. No remote merges/deployments.
3. After closeout, the next owner action is reviewing aggregate119 for a separately authorized merge/release decision.

Protected work: original `/Users/luca/git/Epilogue` stays maincdb776d with local audit/planning files. `/Users/luca/git/Epilogue-secondary` has staged CLAUDE.md, Android SettingsScreen.kt and deployment-example changes on gitbutler/workspace14a753e. Do not absorb/reset/publish them. Inspect other historical worktrees before reuse.
