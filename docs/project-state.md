# Project state

Updated 2026-09-27. Audit baseline: `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`. Original execution base: `e6e62677fe4f5b8f516e226a48080008cafc04e0`. Remote main after continuity merge: `f3eb4b74adf8a97a7db502e5913039f6ec0cdf8b`.

## Objective and authority

Complete the [reliability backlog](work-packages/backlog.md), integrate and verify its output, inspect every PR's review comments, fix actionable findings, and list all PRs. Every worker/reviewer uses **Sol (`gpt-6-sol`)**. Pushes and scoped/aggregate PRs are authorized. The user now explicitly authorizes merging all reliability PRs and verifying main. Releases, deployments, production-content inspection and paid provider calls remain unauthorized. No recurring automation exists.

**The 29 approved reliability packages are complete, integrated, verified and published through PRs.** All available review comments across [46 PRs](work-packages/results/PR-INDEX.md) were inspected; actionable findings are fixed and rejected claims are explained in the [review ledger](work-packages/results/PR-REVIEW-FOLLOWUP.md). No implementation or review worker remains active after this checkpoint.

Aggregate product source `2918931994a05c3fb2d0e1f9e812556361fef479` passed **10 hosted checks with one intentional image-publication skip**, zero failed/pending, at 2026-09-27T21:48:49Z. The final all-PR comment sweep at 21:50:43Z found no additional changes:112 inline comments,58 review bodies,47 issue comments;15 PRs externally merged (seven into prerequisite branches),31 open. The final checkpoint adds only documentation and independently reviewed shared wire tests; production-source equality to the hosted-green revision was verified. Later publication-triggered CI reruns are not represented as completed here.

The combined result is [PR119](https://github.com/LucaKaufmann/Ghostwriter/pull/119); [PR106](https://github.com/LucaKaufmann/Ghostwriter/pull/106) preserves portable continuity. The authorized scoped merges are complete: all 45 scoped PRs74–118 report merged. Their original heads and merge commits are retained in the aggregate history with exact accepted-tree equality. PR119 and actual-main verification remain. No release or deployment. Broader product/release items remain outside this reliability milestone.

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
| Combined integration | Root; complete | `integration`, `codex/backlog-integration`. Hosted-green product checkpoint `2918931`; later test commits264fde1/8a55776 and proof recordaa11343 preserve identical production source. Final publication contains root-owned continuity documents. |
| Backend compatibility | Sol config_sync_closeout; accepted/integrated | Source `ec8ed10`, integrated throughdf4382b: immutable-URL metadata edits retain CAS during DNS failure; legacy caps project at consumption; new URL ports validated.462 tests and clean Sol review. [Evidence](https://github.com/LucaKaufmann/Ghostwriter/blob/2918931994a05c3fb2d0e1f9e812556361fef479/docs/work-packages/results/AGGREGATE-BACKEND-FEED-COMPAT.md). |
| Shared/Android URL admission | Sol android_sync_closeout; accepted/integrated | Source `c63ded1`, integrated8a4f27c: strict new-only admission, exact legacy keys/replay preserved.229 App/59 shared plus one live skip/APK, clean Sol review. [Evidence](https://github.com/LucaKaufmann/Ghostwriter/blob/2918931994a05c3fb2d0e1f9e812556361fef479/docs/work-packages/results/AGGREGATE-FEED-URL-ADMISSION.md). |
| iOS URL admission | Sol ios_sync_closeout; accepted/integrated | Source `470e834` +sharedc63ded1, integrated37d43a0:55 focused/197 workspace/App build,59 shared native/XCFramework. Integrated-source Sol review clean; isolated review's missing-dependency claims resolved by actual combined source. [Evidence](https://github.com/LucaKaufmann/Ghostwriter/blob/2918931994a05c3fb2d0e1f9e812556361fef479/docs/work-packages/results/AGGREGATE-IOS-FEED-URL-ADMISSION.md). |
| Negative-limit boundary proof | Sol android_sync_closeout; accepted/integrated | Test-only source `b247ebb`, integrated8a55776: real JSON through client/use case rejects negative full/incremental/receipt snapshots before relevant writes. Shared62 passed on both platforms; final affected class25/25 on both. Sol review clean. [Evidence](https://github.com/LucaKaufmann/Ghostwriter/blob/aa1134393a4cede7e152e34c7fa8635f8fc08f1b/docs/work-packages/results/AGGREGATE-NEGATIVE-CAP-PROOF.md). |
| Earlier packages and review fixes | Complete | All original 29 outcomes and earlier review corrections remain included. Immutable links in the PR index recover result files without the temporary worktrees. Native deletion invariants remain covered by final native gates. |
| PR review and continuity | Root; complete | All 46 PRs inspected. Latest documentation navigation/range clarifications accepted; alleged44 missing evidence targets rejected after all 46 exact GitHub Contents API requests succeeded. No external review replies or thread-resolution claim. No running workers or automation. |

## Verification baseline

All checks use fixtures/synthetic sources and mocked external providers. Logs are in `/private/tmp/epilogue-backlog-20260927/`.

| Combined gate | Source / command or log | Verified result |
|---|---|---|
| Backend | ec8ed10; `python -m pytest -q`; aggregate-backend-feed-compat-final-full.log | **462 passed**. |
| Live Ktor→FastAPI | 37d43a0; `python3 scripts/verify-feed-sync-contract.py --python /private/tmp/epilogue-runtime-312/bin/python`; final-feed-admission-live-contract.log | **1 passed, no skips**, including native decoding of legacy caps. |
| Shared iOS/framework | c63ded1 product framework; dd244e7/b247ebb test-only proof; `:shared:iosSimulatorArm64Test`, `:shared:assembleEpilogueSharedXCFramework` | Full debug/release XCFramework passed. Shared62 passed; after final control-fixture correction, affected class25/25 passed again. Product framework unchanged. |
| iOS |470e834 +shared c63ded1, integrated37d43a0; `xcodebuildmcp simulator build/test`, schemes Epilogue/Epilogue-Workspace; aggregate-ios-feed-url-admission-{focused,workspace-test,app-build}.log | App build passed;197/197 workspace unit tests, UI target excluded, iPhone16Plus/iOS18.6.55 focused sync tests passed. |
| Browser |06ec2e7; `npm run check`, `npm run test:e2e` with production build; final-web-baseline-closeout-{check,browser}.log |0 errors/warnings;40 browser tests and production build passed. |
| Live reading/listening | 37d43a0; `JOURNEY_PYTHON=/private/tmp/epilogue-runtime-312/bin/python npm run test:e2e -- --config=tests/e2e/reading-listening.playwright.config.ts`; final-feed-admission-journey.log | **1 passed**, real local API/SQLite/browser with synthetic sources and silentMP3. |
| Android |c63ded1 app/product gate; feed-url-full.log; dd244e7/b247ebb shared test-only proof |229 App passed and APK built. Shared62 passed plus one intentional live skip; final affected class25/25 passed again after fixture refinement. |
| Helper |5f3ce6d; `python3 -m unittest discover -s skills/ghostwriter-one-off-podcast/tests`; final-helper-transport.log |20 passed on Python3.14.3; no real API/provider requests. |

Existing Swift concurrency/deprecation warnings, non-failing CoreData checksum messages, Pydantic advisory and historical AsyncMock warning remain. Historical `release_021.sql` whitespace is deliberately preserved; use `git diff --check origin/main..HEAD -- . ':!ghostwriter/tests/fixtures/release_021.sql'` rather than claiming an unqualified whitespace pass.

Runtime: Python3.11 fixture venv `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv` (bin first inPATH and site-packages before localGhostwriter inPYTHONPATH to avoid Alembic shadowing); requirements-onlyPython3.12 `/private/tmp/epilogue-runtime-312/bin/python`; JDK17 `/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`; both AndroidSDK variables `/private/tmp/epilogue-backlog-20260927/android-sdk`; Tuist4.152/Xcode26.5/xcodebuildmcp2.3/iOS18.6; Node24/npm11 locked dependencies.

No real-provider audio-quality, physical-device background timing, KOReader hardware, arm64-container-runtime, signing/distribution or production-restore claim. Generation gates are process-local. Android retry identity uses an isolated read-only internal WorkManager2.9 periodCount adapter: dependency upgrades must reverify its retry/ack lifecycle. Reads fail conservatively when identity is unavailable.

## Schema and branch coordination

Alembic026 feed versions/receipts,027 source acknowledgements,028 one-off ownership; Room9 feed outbox,10 delivery,11 scheduled coverage; frozen SwiftDataV1→V2 feed sync→V3 delivery. Root allocates revisions. No new revision for response projection or diagnosticsJSON mode.

Frozen comparison branches: `codex/review-fixes-verified-base`6f9a328; `codex/review-followup-base`ae0e8dd; `codex/ios-sync-review-verified-base`6e232cd. These are PR bases, not current main. Historical notes/results remain recoverable via immutable PR-index links; ignored `tasks/` can be rebuilt from this checkpoint.

## Exact next action

Authorized merge milestone active: merge the history-reconciled PR119, then verify actual main in an isolated checkout. All 45 scoped PRs are merged; independent Sol graph audit is complete. Root owns mutations and the [merge plan](work-packages/merge-plan.md). PR106/4117156228 stale review status corrected at the merge boundary. Logs/snapshots: `/private/tmp/epilogue-backlog-20260927/merge-closeout/`. Original implementation packages remain complete; do not restart them from historical checkboxes.

Protected work: original `/Users/luca/git/Epilogue` stays maincdb776d with local audit/planning files. `/Users/luca/git/Epilogue-secondary` has staged CLAUDE.md, Android SettingsScreen.kt and deployment-example changes on gitbutler/workspace14a753e. Do not absorb/reset/publish them. Inspect other historical worktrees before reuse.
