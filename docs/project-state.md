# Project state

Updated 2026-09-27. Audit baseline: `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`; execution base: `origin/main` at `e6e62677fe4f5b8f516e226a48080008cafc04e0` (only privacy-policy documentation changed between these).

## Objective and authority

Complete the [autonomous reliability backlog](work-packages/backlog.md), verify/integrate the work, and list every PR. One orchestrator owns coordination and shared documents; all workers and independent reviews use **Sol (`gpt-6-sol`)**. Branch pushes and scoped PR creation are authorized. Merges, releases, deployments, paid provider calls and production-content inspection are not authorized. No recurring automation is configured.

The [restart audit](restart-audit.md) is a dated baseline, not present-tense proof. [Orchestration instructions](project-orchestrator-prompt.md) and [worker brief template](work-packages/worker-prompt.md) define continuity and ownership. `tasks/` is ignored; recreate local plans/lessons from this checkpoint if absent. Preserve uncommitted work.

## Confirmed product decisions

The owner selected on 2026-09-27:

- Concurrent feed edits preserve the newer server version and retain the conflicting local proposal for explicit resolution.
- Normal local Android/iOS editions deliver each article once, even after digest history deletion. Explicit regeneration may repeat articles.
- Episode-referenced digests are preserved: block manual deletion and skip scheduled deletion until references are removed. Unrelated historical orphan files remain untouched.

The product turns chosen sources into finite reading/listening editions. Primary audience/platform/release target and future tenancy remain open; no reliability package authorizes expansion. Feeds/config/digests are largely installation-wide; podcast ownership is more granular. Preserve offline behavior and already-enabled feature-flag configurations.

## Task ledger

Worker worktrees use `/private/tmp/epilogue-backlog-20260927/` unless noted. Exact PR heads are recoverable from GitHub; do not infer integration from a worker's completion message.

| Package | Owner/status | Branch, evidence and next action |
|---|---|---|
| ENV-01 | Sol; accepted | `codex/env-01-hermetic-tests`, `de68d540ea67383a3843b8085659d29dcf19baaa`; [PR75](https://github.com/LucaKaufmann/Ghostwriter/pull/75), base main. 252 tests; isolated installs; final Sol clean; all matching CI passed. Worktree `/private/tmp/epilogue-wave1-20260927/env-01`. |
| AUTH-01 | Sol; accepted | `codex/auth-01-auth-lifecycle`, `1da3bb49e4e196f2bf7008a2ffed45da5417f801`; [PR76](https://github.com/LucaKaufmann/Ghostwriter/pull/76), base ENV branch. 105 focused tests; Sol clean; all CI passed. Worktree `/private/tmp/epilogue-wave1-20260927/auth-01`. |
| HELPER-01 | Sol; accepted | `codex/helper-01-origin-guard`, `4267ed88d4a3002f9d0325908945a204cbeda799`; [PR74](https://github.com/LucaKaufmann/Ghostwriter/pull/74), base main. 15 synthetic transport tests on Python3.11/3.14; Sol clean. No CI trigger for helper paths yet. Worktree `/private/tmp/epilogue-wave1-20260927/helper-01`. |
| INGEST-01 | Sol + root review corrections; accepted | `ingest-01`, `codex/ingest-01-source-editions`, `679bd909d5780e55be21d8ea5347e3ea6a9a54d3`; [PR77](https://github.com/LucaKaufmann/Ghostwriter/pull/77), base ENV branch. 35 focused tests; Sol clean; backend/frontend/image/health CI passed. |
| KO-01 | Root; last review correction | `ko-01`, `codex/ko-01-owned-downloads`, worker24b50f2 plus tested finalization-identity check. Latest full Sol review left only replacement adoption between API return and stamp; host Lua harness passes after root fix, targeted review `ko-review-stamp.*` running. Hardware unverified. |
| WEB-01 | Sol + root; accepted | `web-01`, `codex/web-01-browser-checks`, `67acec4e0f3607a7c0eedd318c84fd022e55a803`; [PR78](https://github.com/LucaKaufmann/Ghostwriter/pull/78), ready, base main. Local13 browser tests/check/build pass; all Darwin/Linux visuals inspected; hosted browser/backend/frontend/image checks pass, final Sol review clean. |
| BUILD-NATIVE | Sol + root; accepted | `build-native`, `codex/build-native-baseline`, `8c7c148ab5bc9d59f7305f7b64d0e235e9d60f6f`; [PR79](https://github.com/LucaKaufmann/Ghostwriter/pull/79), ready, base main. Local80 Android/19 shared/70 iOS pass, XCFramework/regenerated app builds; hosted Android/iOS run36311548617 passed; final Sol clean. Initial SDKtools CI failure fixed. |
| CONTRACT-01 | Root; accepted design | `contract-01`, `codex/contract-01-sync-delivery`, `cc933f1029e17a85e8edaa74950bb59206bb8757`; [PR82](https://github.com/LucaKaufmann/Ghostwriter/pull/82), main. Final Sol rollback-only review clean after full contract review. No product code. Reserves Alembic026, Room9/10, SwiftDataV1/V2/V3. |
| CONTINUITY-01 | Root; published | `project-continuity`, `codex/project-continuity`; [PR80](https://github.com/LucaKaufmann/Ghostwriter/pull/80), main. Audit/backlog/briefs/checkpoints portable on branch; no product changes. Root updates this PR at milestones. |
| RETENTION-01 | Sol + root; accepted design | `retention-01`, `codex/retention-01-deletion-contract`, head7ceada0; [PR81](https://github.com/LucaKaufmann/Ghostwriter/pull/81), baseENV. Sol clean,94 existing tests + synthetic orphan probe; all hosted checks passed. Contract/fixtures only; RETENTION02 implementation ready to dispatch. |
| FETCH-01 | Root; review corrections pending | `fetch-01`, `codex/fetch-01-bounded-requests`, baseENV; head`dfa05d6d45d14f46b46d4af934830ff2637feed4`,143 focused pass. Final review found upstream decoding ValueError mapping, Content-Location loss, surviving DNS worker resource bound and proxy/CA compatibility. Correct before PR; no active worker. |
| WEB-02 | `/root/web_02_closeout`; correcting | `web-02`, `codex/web-02-session-recovery`, baseWEB01, head44709e49. Worker invalidating old-session successful private downloads/results before callbacks; tests and review pending. |
| ANDROID-FILES | `/root/android_files_closeout`; correcting | `android-files`, `codex/android-files-unique-artifacts`, baseBUILD-NATIVE8c7c148, headd5304a9.88 Android/19 shared pass. Latest review found EPUB leak after generation but before history finalization; worker owns cleanup and regression tests. No PR yet. |
| RUNTIME-01 | Root; hosted verification | `runtime-01`, `codex/runtime-01-controlled-build`, baseENV, head48cb611; [PR83](https://github.com/LucaKaufmann/Ghostwriter/pull/83), draft. Final Sol clean;33 backend/Node checks/host migrations+health pass; hosted backend/frontend passed, amd64 image build/health pending run36313233006. Local Docker unavailable; arm64 unverified. |
| RETENTION-02 | `/root/retention_02`; implementing | `retention-02`, `codex/retention-02-safe-deletion`, base`7ceada001571a6ad8b7509fb42c03f98c60dd447` (PR81). Own digest API/cleanup/new service plus narrow episode/feedback coordination seams. No schema changes. |
| WALLABAG-01 | Root; review | `wallabag-01`, `codex/wallabag-01-token-isolation`, headfc09bdb, baseINGEST679bd90. Immutable effective configuration and instance token cache.32 focused tests pass; Sol27222 running. |
| Remaining backlog | Unstarted | Dependency order and scoped acceptance criteria in [backlog](work-packages/backlog.md). First-wave completion is not full backlog completion. |

Per-package tracked result files are `docs/work-packages/results/<ID>.md` on their PR branches. All created PRs are attached to the orchestrator task. Main has not been merged or modified by implementation workers.

## Integration and verification baseline

- Local combined branch `codex/backlog-integration`, worktree `integration`, head `623a3ab`, contains ENV/AUTH/HELPER/INGEST/WEB01/BUILD-NATIVE. The latter web/native additions match independently passing branches; no redundant combined backend rerun was required for their frontend/build-only changes. Backend **276 passed** before INGEST's later test-only assertion strengthening; strengthened focused suite **35 passed**. First-wave-only integration had backend264/helper15 passed. This is local integration, no remote main merge.
- Backend fixture runtime: Python3.11.16 venv `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv`. Run from integration/ghostwriter with venv `bin` first in PATH and venv `site-packages` then current ghostwriter path in PYTHONPATH to avoid source `alembic` shadowing installed CLI. No real provider calls. Warnings: Starlette/httpx deprecation, Pydantic ReadOnly advisory, intermittent historical AsyncMock warning.
- ENV isolated editable/requirements installs and `pip check` passed. SQLModel `<0.0.32` preserves existing naive timestamps; observed failures on0.0.46/0.0.47, not a claim about every intervening release. YouTube transcript API1.2.4 exercised offline. External yt-dlp/whisper-cli absent locally; no real audio validation.
- Native current local baseline supersedes the audit's environment-blocked checks: JDK17.0.17, Gradle8.5, Android platform35/build-tools34, Tuist4.152.0, Xcode26.5, iPhone16ProMax/iOS18.6. Task SDK at `android-sdk`; XCFramework built before Tuist generation. Android XML tests need scoped Robolectric runtime; AIServices exact error-case test and Ghostwriter absoluteHTTP(S) string URL guard fix exposed baseline failures. Swift warnings remain outside scope. Hosted Android/shared and iOS simulator CI now passed at8c7c148.
- Browser checks are fixture UI checks; backend+frontend integration and generated audio remain unverified. KOReader hardware unverified. No signing/distribution/production validation performed.

## Schema and ownership reservations

Accepted CONTRACT-01 design reserves Alembic **026** after025 for feed versions/clock/mutation receipts; Room **9** for sync/outbox after8, then **10** for delivery identity; SwiftData current schema captured asV1, V2 sync/outbox, V3 delivery. Exact model/file paths are in the contract branch. Root must recheck integrated schema head before dispatch; no worker independently allocates revisions. RETENTION design must coordinate any additional schema or shared cleanup.py edits. In particular current cleanup deletes feed tombstones after30days, incompatible with indefinite offline replay; server sync stage must stop that purge.

## Recovery and next action

1. Recover workers/review processes before restarting. Active Sol workers: WEB02 closeout, ANDROIDFILES closeout, RETENTION02. Root process handles cannot be polled by workers.
2. Pending reviews: KO targeted ownership stamp correction (`ko-review-stamp.*`); Wallabag27222. Runtime PR83 hosted amd64 image/health pending. FETCH143-test snapshot needs four reviewed compatibility/resource corrections before publication. Resume FETCH worker when a slot frees.
3. Finish these scoped packages, integrate accepted branches, then dispatch dependency-ready INPUT, recovery/media, native/sync stages. Sync server must wait for INPUT and RETENTION02 cleanup ownership. Continue full backlog, list every PR. Held personal DEPLOY-01 remains outside scope. No merge/deploy.

Local original checkout `/Users/luca/git/Epilogue` remains main atcdb776d with local audit/planning files. This documentation PR makes copies portable. `/Users/luca/git/Epilogue-secondary` has staged CLAUDE.md, Android SettingsScreen.kt and deployment-example edits on `gitbutler/workspace` at14a753e; preserve them, do not absorb/discard. Other historical registered worktrees were clean at inspection, but their existence is not evidence of active workers or integrated changes. Reinspect if overlapping work becomes relevant.
