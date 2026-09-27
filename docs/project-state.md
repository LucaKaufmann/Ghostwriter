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
| KO-01 | Root; final review | `ko-01`, `codex/ko-01-owned-downloads`, heade317450. Ownership now compares finalized identity and stream hash; unreadable ownership retains file for manual collision resolution. Host Lua passes; final targeted Sol68072 (`ko-review-unreadable.*`) running. Hardware unverified. |
| WEB-01 | Sol + root; accepted | `web-01`, `codex/web-01-browser-checks`, `67acec4e0f3607a7c0eedd318c84fd022e55a803`; [PR78](https://github.com/LucaKaufmann/Ghostwriter/pull/78), ready, base main. Local13 browser tests/check/build pass; all Darwin/Linux visuals inspected; hosted browser/backend/frontend/image checks pass, final Sol review clean. |
| BUILD-NATIVE | Sol + root; accepted | `build-native`, `codex/build-native-baseline`, `8c7c148ab5bc9d59f7305f7b64d0e235e9d60f6f`; [PR79](https://github.com/LucaKaufmann/Ghostwriter/pull/79), ready, base main. Local80 Android/19 shared/70 iOS pass, XCFramework/regenerated app builds; hosted Android/iOS run36311548617 passed; final Sol clean. Initial SDKtools CI failure fixed. |
| CONTRACT-01 | Root; accepted design | `contract-01`, `codex/contract-01-sync-delivery`, `cc933f1029e17a85e8edaa74950bb59206bb8757`; [PR82](https://github.com/LucaKaufmann/Ghostwriter/pull/82), main. Final Sol rollback-only review clean after full contract review. No product code. Reserves Alembic026, Room9/10, SwiftDataV1/V2/V3. |
| CONTINUITY-01 | Root; published | `project-continuity`, `codex/project-continuity`; [PR80](https://github.com/LucaKaufmann/Ghostwriter/pull/80), main. Audit/backlog/briefs/checkpoints portable on branch; no product changes. Root updates this PR at milestones. |
| RETENTION-01 | Sol + root; accepted design | `retention-01`, `codex/retention-01-deletion-contract`, head7ceada0; [PR81](https://github.com/LucaKaufmann/Ghostwriter/pull/81), baseENV. Sol clean,94 existing tests + synthetic orphan probe; all hosted checks passed. Contract/fixtures only; RETENTION02 implementation ready to dispatch. |
| FETCH-01 | Root; final review | `fetch-01`, `codex/fetch-01-bounded-requests`, baseENV; head`bd5e31590f889578ff0e416183443539c311c59e`,149 focused tests pass. Corrected decoding fallback, Content-Location, bounded isolated DNS pool, environment proxy/CA support. Targeted Sol43533 (`fetch-review-compat.*`) running. |
| WEB-02 | Root; accepted with baseline CI failure | `web-02`, `codex/web-02-session-recovery`, head2513812; [PR86](https://github.com/LucaKaufmann/Ghostwriter/pull/86), baseWEB01. Local21 browser +check/build, final Sol clean; hosted browser/frontend pass. Inherited backend6 failures are SQLModel naive-timestamp incompatibility fixed by ENV75; cumulative ENV integration285 passes. Image pending; no code regression claimed. |
| ANDROID-FILES | Root; accepted, hosted checks finishing | `android-files`, `codex/android-files-unique-artifacts`, baseBUILD-NATIVE8c7c148, headfaa3927; [PR85](https://github.com/LucaKaufmann/Ghostwriter/pull/85).91 Android/19 shared pass, final Sol clean after history-finalization cleanup. Hosted Android pass, iOS pending36313693162. Process death orphan limitation documented; emulatorUI not run. |
| RUNTIME-01 | Root; accepted | `runtime-01`, `codex/runtime-01-controlled-build`, baseENV, head6a4f980; [PR83](https://github.com/LucaKaufmann/Ghostwriter/pull/83), ready. Sol clean;33 backend/Node/host migration+health pass; hosted backend/frontend/amd64 image+health passed atimplementation48cb611 run36313233006. Arm64 unverified, localDocker unavailable. |
| RETENTION-02 | `/root/retention_02`; implementing | `retention-02`, `codex/retention-02-safe-deletion`, base`7ceada001571a6ad8b7509fb42c03f98c60dd447` (PR81). Own digest API/cleanup/new service plus narrow episode/feedback coordination seams. No schema changes. |
| WALLABAG-01 | Root; accepted | `wallabag-01`, `codex/wallabag-01-token-isolation`, head522bf75, baseINGEST679bd90; [PR84](https://github.com/LucaKaufmann/Ghostwriter/pull/84).32 focusedtests, finalSolclean, allhostedchecks passed; cumulativebackend285passed. |
| MEDIA-01 | Root; review | `media-01`, `codex/media-01-single-flight`, head1c5655faddd3731ee13b79ac9f977fb238def6d8, baseENV. Deterministic original overlap reproduced;24 focusedtests pass. Sol49969 (`media-review.*`) running. |
| ANDROID-OBSERVE | `/root/android_observe`; implementing | `android-observe`, `codex/android-observe-lifecycle`, basefaa3927(PR85). OwnSettingsViewModel/DigestScheduler exact work-ID observation/lifecycle tests; no source selection changes. |
| RECOVERY-01 | `/root/recovery_01`; investigating | `recovery-01`, `codex/recovery-01-fault-contract`, baseINGEST679bd90. Own new fault fixtures/contract only; no pipeline production edits. |
| Remaining backlog | Unstarted | Dependency order and scoped acceptance criteria in [backlog](work-packages/backlog.md). First-wave completion is not full backlog completion. |

Per-package tracked result files are `docs/work-packages/results/<ID>.md` on their PR branches. All created PRs are attached to the orchestrator task. Main has not been merged or modified by implementation workers.

## Integration and verification baseline

- Local combined branch `codex/backlog-integration`, worktree `integration`, head `c86262e`, contains ENV/AUTH/HELPER/INGEST/WEB01/BUILD-NATIVE/WALLABAG/RUNTIME/ANDROID-FILES/WEB02. Backend **285 passed** at940e050 after Wallabag/runtime integration; subsequent web/native-only additions match independently passing branches (Android91/shared19, browser21), with no redundant backend rerun. Earlier ingestion focused suite35 passed. First-wave-only integration had backend264/helper15 passed. This is local integration, no remote main merge.
- Backend fixture runtime: Python3.11.16 venv `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv`. Run from integration/ghostwriter with venv `bin` first in PATH and venv `site-packages` then current ghostwriter path in PYTHONPATH to avoid source `alembic` shadowing installed CLI. No real provider calls. Warnings: Starlette/httpx deprecation, Pydantic ReadOnly advisory, intermittent historical AsyncMock warning.
- ENV isolated editable/requirements installs and `pip check` passed. SQLModel `<0.0.32` preserves existing naive timestamps; observed failures on0.0.46/0.0.47, not a claim about every intervening release. YouTube transcript API1.2.4 exercised offline. External yt-dlp/whisper-cli absent locally; no real audio validation.
- Native current local baseline supersedes the audit's environment-blocked checks: JDK17.0.17, Gradle8.5, Android platform35/build-tools34, Tuist4.152.0, Xcode26.5, iPhone16ProMax/iOS18.6. Task SDK at `android-sdk`; XCFramework built before Tuist generation. Android XML tests need scoped Robolectric runtime; AIServices exact error-case test and Ghostwriter absoluteHTTP(S) string URL guard fix exposed baseline failures. Swift warnings remain outside scope. Hosted Android/shared and iOS simulator CI now passed at8c7c148.
- Browser checks are fixture UI checks; backend+frontend integration and generated audio remain unverified. KOReader hardware unverified. No signing/distribution/production validation performed.

## Schema and ownership reservations

Accepted CONTRACT-01 design reserves Alembic **026** after025 for feed versions/clock/mutation receipts; Room **9** for sync/outbox after8, then **10** for delivery identity; SwiftData current schema captured asV1, V2 sync/outbox, V3 delivery. Exact model/file paths are in the contract branch. Root must recheck integrated schema head before dispatch; no worker independently allocates revisions. RETENTION design must coordinate any additional schema or shared cleanup.py edits. In particular current cleanup deletes feed tombstones after30days, incompatible with indefinite offline replay; server sync stage must stop that purge.

## Recovery and next action

1. Recover workers/review processes before restarting. Active Sol workers: RETENTION02, ANDROID-OBSERVE, RECOVERY01. Root handles cannot be polled by workers.
2. Root reviews: KO68072 (`ko-review-unreadable.*`), FETCH43533 (`fetch-review-compat.*`), MEDIA49969 (`media-review.*`). Inspect/publish accepted results. RETENTION02 nearly frozen; root requested failed-empty-filename cleanup and bounded lock registry. Hosted PR85 iOS and PR86 image pending; PR86 backend baseline requires ENV75.
3. Resume dependency-ready INPUT after FETCH, then staged sync server (must wait for RETENTION02 cleanup ownership), KMP and native sync/delivery. No work has started on those schema stages. Continue full backlog and list every PR; DEPLOY01 held. No merge/deploy.

Local original checkout `/Users/luca/git/Epilogue` remains main atcdb776d with local audit/planning files. This documentation PR makes copies portable. `/Users/luca/git/Epilogue-secondary` has staged CLAUDE.md, Android SettingsScreen.kt and deployment-example edits on `gitbutler/workspace` at14a753e; preserve them, do not absorb/discard. Other historical registered worktrees were clean at inspection, but their existence is not evidence of active workers or integrated changes. Reinspect if overlapping work becomes relevant.
