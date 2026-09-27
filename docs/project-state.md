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
| KO-01 | `/root/ko_01`; review corrections | `ko-01`, `codex/ko-01-owned-downloads`, last reviewed head `2e4894b`. Lua harness passes but Sol found real settings-write error, finalization collision, same-size edited-file ownership gaps. Worker correcting before final review/PR. |
| WEB-01 | `/root/web_01`; Linux evidence pending | `web-01`, `codex/web-01-browser-checks`, `0be75ac`; [draft PR78](https://github.com/LucaKaufmann/Ghostwriter/pull/78), base main. Local check/build and 13 browser tests pass; Darwin visuals inspected. Worker obtaining/reviewing Linux baselines; final Sol review still required. |
| BUILD-NATIVE | `/root/build_native`; hosted CI/review | `build-native`, `codex/build-native-baseline`, `5d052b004f954b8aa0308f1a6dd6481d1fa068ca`; [draft PR79](https://github.com/LucaKaufmann/Ghostwriter/pull/79), base main. Local Android80/shared19/iOS70 pass, XCFramework and regenerated simulator build pass. Hosted SDK installer fails on retired `tools` package; accepted workflow correction pending. Sol review root session54657. |
| CONTRACT-01 | Root; design review | `contract-01`, `codex/contract-01-sync-delivery`, `d07b4d4`; `docs/contracts/feed-sync-and-local-delivery.md` on that branch. Sol review root session5912. Exact schema reservations below. Correct draft title-nullability typo and ensure tombstone purge disabled before acceptance. No implementation dispatched. |
| CONTINUITY-01 | Root; documentation publication | `project-continuity`, `codex/project-continuity`; this checkpoint, historical audit and full worker briefs. Documentation only. |
| Remaining backlog | Unstarted | Dependency order and scoped acceptance criteria in [backlog](work-packages/backlog.md). First-wave completion is not full backlog completion. |

Per-package tracked result files are `docs/work-packages/results/<ID>.md` on their PR branches. All created PRs are attached to the orchestrator task. Main has not been merged or modified by implementation workers.

## Integration and verification baseline

- Local combined branch `codex/backlog-integration`, worktree `integration`, head `b65e8cb`, contains ENV/AUTH/HELPER/INGEST. Backend **276 passed** before INGEST's later test-only assertion strengthening; strengthened focused suite **35 passed**. First-wave-only integration had backend264/helper15 passed. This is local integration, no remote main merge.
- Backend fixture runtime: Python3.11.16 venv `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv`. Run from integration/ghostwriter with venv `bin` first in PATH and venv `site-packages` then current ghostwriter path in PYTHONPATH to avoid source `alembic` shadowing installed CLI. No real provider calls. Warnings: Starlette/httpx deprecation, Pydantic ReadOnly advisory, intermittent historical AsyncMock warning.
- ENV isolated editable/requirements installs and `pip check` passed. SQLModel `<0.0.32` preserves existing naive timestamps; observed failures on0.0.46/0.0.47, not a claim about every intervening release. YouTube transcript API1.2.4 exercised offline. External yt-dlp/whisper-cli absent locally; no real audio validation.
- Native current local baseline supersedes the audit's environment-blocked checks: JDK17.0.17, Gradle8.5, Android platform35/build-tools34, Tuist4.152.0, Xcode26.5, iPhone16ProMax/iOS18.6. Task SDK at `android-sdk`; XCFramework built before Tuist generation. Android XML tests need scoped Robolectric runtime; AIServices exact error-case test and Ghostwriter absoluteHTTP(S) string URL guard fix exposed baseline failures. Swift warnings remain outside scope. Hosted CI is not yet green.
- Browser checks are fixture UI checks; backend+frontend integration and generated audio remain unverified. KOReader hardware unverified. No signing/distribution/production validation performed.

## Schema and ownership reservations

CONTRACT-01 design, still under review, reserves Alembic **026** after025 for feed versions/clock/mutation receipts; Room **9** for sync/outbox after8, then **10** for delivery identity; SwiftData current schema captured asV1, V2 sync/outbox, V3 delivery. Exact model/file paths are in the contract branch. Root must recheck integrated schema head before dispatch; no worker independently allocates revisions. RETENTION design must coordinate any additional schema or shared cleanup.py edits. In particular current cleanup deletes feed tombstones after30days, incompatible with indefinite offline replay; server sync stage must stop that purge.

## Recovery and next action

1. Inspect live workers and running root reviews before restarting. Root process handles cannot be polled from workers. Review logs live beside worktrees; temporary logs may disappear, so lasting results belong on PR branches.
2. Finish accepted KO corrections and final Sol review; inspect WEB Linux candidates and green CI; finish BUILD-NATIVE hosted setup and final Sol review; resolve CONTRACT-01 review and publish frozen design.
3. Dispatch dependency-ready FETCH/INPUT, retention design, Android files/observation and sequential sync stages with exact base/owned paths. Continue until the backlog is verified; report all PRs then. Held personal DEPLOY-01 remains outside scope.

Local original checkout `/Users/luca/git/Epilogue` remains main atcdb776d with local audit/planning files. This documentation PR makes copies portable. `/Users/luca/git/Epilogue-secondary` has staged CLAUDE.md, Android SettingsScreen.kt and deployment-example edits on `gitbutler/workspace` at14a753e; preserve them, do not absorb/discard. Other historical registered worktrees were clean at inspection, but their existence is not evidence of active workers or integrated changes. Reinspect if overlapping work becomes relevant.
