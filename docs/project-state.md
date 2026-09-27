# Project state

Updated 2026-09-27. Audit baseline: `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`. Original execution base: `e6e62677fe4f5b8f516e226a48080008cafc04e0`. Remote main refreshed: `86d3efdaf2506c700b3613dfd0bd9425a05ee8ec`.

## Objective and authority

Complete the [reliability backlog](work-packages/backlog.md), integrate and verify its output, inspect every PR's review comments, fix actionable findings, and list all PRs. Every worker/reviewer uses **Sol (`gpt-6-sol`)**. Pushes and scoped/aggregate PRs are authorized. Remote merges, releases, deployments, production-content inspection and paid provider calls are not authorized. No recurring automation exists.

**All 29 original package outcomes are implemented, integrated and published through45 scoped PRs (#74–118), plus [aggregate PR119](https://github.com/LucaKaufmann/Ghostwriter/pull/119) against main.** All actionable findings from the latest paginated46-PR comment sweep are corrected. Final combined gates passed: iOS183 workspace tests/App build and Android208 App/58shared tests/debugAPK. Unaffected backend/browser/shared/helper gates remain valid. The audit is historical; [PR index](work-packages/results/PR-INDEX.md) and [review dispositions](work-packages/results/PR-REVIEW-FOLLOWUP.md) link evidence. Fifteen PRs74–88 were externally merged;76/77/81/83/84/85/88 landed in prerequisite branches. Main contains74/75/78/79/80/82/86/87. Root has not remotely merged anything.

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
| Combined integration | Root; all code accepted/verified, hosted closeout pending | `integration`, branch `codex/backlog-integration`, code f53d7d4. All original outcomes and accepted review corrections integrated. This checkpoint publishes the accepted final Android/iOS changes through aggregate119. Inspect its current-head hosted checks before closeout. |
| Android scheduling/retry | Accepted/published/combined verified | `review-android-delivery`, PR118; accepted16d63a6 failed-receipt recovery plus661cbae cancellation-only boot correction. Both independently reviewed. Final combined gate atf53d7d4 passed208 App/58shared tests+1intentional skip/debugAPK. PR118661cbae is published. Internal WorkManager2.9 retry identity coupling remains explicit. |
| Aggregate iOS URL revert | Accepted/combined verified | `aggregate-ios-url-revert`, branch `codex/aggregate-ios-url-revert`:045cf734+8766275, integratedc721b25/0de22a0. Transient URL edits retain original binding; configured-URL/generation guards prevent consuming old-server proposals. Existing integrity suspensions remain. Sol review clean; combined183workspace tests/Appbuild passed. Included in119. |
| Earlier accepted fixes | Integrated and published | Backend1137871e7a legacy cap read projection; web111acf7abc draft preservation/baseline; iOS116879f237 explicit regeneration recovery;11225e2b1d Android correction defaults;115c526cb6 complete iOS re-add serialization;108/109/114 backend publication/DNS/ownership;117304f964 helper download. Individual immutable results/dispositions carry evidence. |
| Review sweep | Root; findings corrected, final refresh pending | Latest full paginated74–119 sweep inspected inline comments, review bodies and issue comments.119/4116430726 fixed by the accepted iOS stack;118/4116469560 fixed661cbae;106/4116431240 routing handoff corrected against source. No external review replies. Refresh after publication for newly arrived findings/current CI. |
| Continuity | Root; final checkpoint local | `project-continuity`, PR106; this final checkpoint is also included in119. Copy root-owned documents only. Do not overwrite implementation result files. |

## Verification baseline

All checks use fixtures/synthetic sources and mocked external providers. Logs are in `/private/tmp/epilogue-backlog-20260927/`.

| Combined gate | Source / command or log | Verified result |
|---|---|---|
| Backend | f371a84; `python -m pytest -q`; final-backend-legacy-cap-combined.log | **451 passed**. |
| Live Ktor→FastAPI | f371a84; `python3 scripts/verify-feed-sync-contract.py --python /private/tmp/epilogue-runtime-312/bin/python`; final-live-legacy-cap-contract.log | **1 passed, no skips**, including native decoding of legacy caps. |
| Shared iOS/framework | d455f05; `:shared:iosSimulatorArm64Test :shared:assembleEpilogueSharedXCFramework --offline --no-daemon` |58passed; full debug/release XCFramework succeeded. Later shared changes only strengthen Android live-test fixture. |
| iOS |0de22a0; `xcodebuildmcp simulator build/test`, schemes Epilogue/Epilogue-Workspace; final-ios-url-{app-build,workspace-test}.log | App build passed;183/183 workspace unit tests, UI target excluded, V3sim3B168BD4. Later Android-only source changes do not affect this gate. |
| Browser |06ec2e7; `npm run check`, `npm run test:e2e` with production build; final-web-baseline-closeout-{check,browser}.log |0errors/warnings;40browser tests and production build passed. |
| Live reading/listening | f371a84; `JOURNEY_PYTHON=/private/tmp/epilogue-runtime-312/bin/python npm run test:e2e -- --config=tests/e2e/reading-listening.playwright.config.ts`; final-web-baseline-closeout-journey.log | **1 passed**, real local API/SQLite/browser with synthetic sources and silentMP3. |
| Android | f53d7d4; `:app:testDebugUnitTest :shared:testDebugUnitTest :app:assembleDebug --offline --no-daemon`; final-android-boot-closeout.log | **208 App/58 shared passed**,1intentional live skip; debug APK. |
| Helper |5f3ce6d; `python3 -m unittest discover -s skills/ghostwriter-one-off-podcast/tests`; final-helper-transport.log |20passed on Python3.14.3; no real API/provider requests. |

Existing Swift concurrency/deprecation warnings, non-failing CoreData checksum messages, Pydantic advisory and historical AsyncMock warning remain. Historical `release_021.sql` whitespace is deliberately preserved; use `git diff --check origin/main..HEAD -- . ':!ghostwriter/tests/fixtures/release_021.sql'` rather than claiming an unqualified whitespace pass.

Runtime: Python3.11 fixture venv `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv` (bin first inPATH and site-packages before localGhostwriter inPYTHONPATH to avoid Alembic shadowing); requirements-onlyPython3.12 `/private/tmp/epilogue-runtime-312/bin/python`; JDK17 `/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`; both AndroidSDK variables `/private/tmp/epilogue-backlog-20260927/android-sdk`; Tuist4.152/Xcode26.5/xcodebuildmcp2.3/iOS18.6; Node24/npm11 locked dependencies.

No real-provider audio-quality, physical-device background timing, KOReader hardware, arm64-container-runtime, signing/distribution or production-restore claim. Generation gates are process-local. Android retry identity uses an isolated read-only internal WorkManager2.9 periodCount adapter: dependency upgrades must reverify its retry/ack lifecycle. Reads fail conservatively when identity is unavailable.

## Schema and branch coordination

Alembic026 feed versions/receipts,027 source acknowledgements,028 one-off ownership; Room9 feed outbox,10 delivery,11 scheduled coverage; frozen SwiftDataV1→V2 feed sync→V3 delivery. Root allocates revisions. No new revision for response projection or diagnosticsJSON mode.

Frozen comparison branches: `codex/review-fixes-verified-base`6f9a328; `codex/review-followup-base`ae0e8dd; `codex/ios-sync-review-verified-base`6e232cd. These are PR bases, not current main. Historical notes/results remain recoverable via immutable PR-index links; ignored `tasks/` can be rebuilt from this checkpoint.

## Exact next action

1. Inspect aggregate119 current-head hosted checks and any newly arrived review comments after final publication; record the exact source revision and disposition. All local acceptance gates and independent code reviews passed.
2. Report29 completed packages and all46 PRs. Remote merge/release/deployment remain separate and unauthorized.

Protected work: original `/Users/luca/git/Epilogue` stays maincdb776d with local audit/planning files. `/Users/luca/git/Epilogue-secondary` has staged CLAUDE.md, Android SettingsScreen.kt and deployment-example changes on gitbutler/workspace14a753e. Do not absorb/reset/publish them. Inspect other historical worktrees before reuse.
