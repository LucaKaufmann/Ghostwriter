# Autonomous PR backlog

Prepared 2026-09-27 against `main` at `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`. This is an execution plan derived from the [restart audit](../restart-audit.md), not a claim of implemented fixes. Current affected source was checked during preparation. Revalidate each finding against the actual launch revision.

## Execution agreement

The user requested a work list ready for autonomous subagents to deliver PRs. The user subsequently authorized completing the full backlog through PRs. Implementation proceeds in dependency order. PR creation/push is part of those assignments. Merging, releases, deployments, registry publication, production inspection, and paid provider calls are outside this authority.

All packages inherit the [worker prompt](worker-prompt.md). The orchestrator owns dispatch, dependency integration, shared planning documents, migration revision allocation, review, and acceptance. The user does not relay agent messages or reconcile changes.

- One isolated worktree and branch per package, from a verified base. Suggested branch: `codex/<lowercase-id>-<short-slug>`. Never change branch in the shared main checkout or reuse dirty historical worktrees.
- One active owner per mutable area. Named tests belong to their package. Global fixtures, schemas, API contracts, dependency manifests, lockfiles, CI workflows, Tuist manifests, and planning documents require explicit ownership. A worker may request a narrow ownership expansion from the orchestrator; absence from a list is not permission to edit globally.
- Every package may add its own `docs/work-packages/results/ID.md`. Workers may update only worktree-local ignored task notes. Root alone updates this backlog and `docs/project-state.md`.
- Backend migration head was `025` at the baseline; never preassign `026` to several workers. Root allocates the next revision at integration. SQLModel/Alembic changes must be paired, sequential, idempotent, registered, and tested on fresh and previous-revision databases. No destructive SQLite downgrade.
- Explicit dependencies mean **verified integration**, not just an open PR. Root may use a deliberately stacked base with exact dependency commits and a disclosed PR target; otherwise wait for authorized merge. Creating a PR never silently authorizes its merge. For combined verification root may assemble a disposable local integration branch without merging main or deploying.
- Ship one PR per bounded package, with meaningful regression evidence. A design/investigation package delivers a documentation/test-harness PR. If the finding is obsolete, return current evidence; do not manufacture a code change or empty PR.
- Required verification unavailable means draft/unverified, not done. Resolve tool availability before scheduling native dependent work. Preserve already-enabled feature-flagged configurations.

## Scheduling and ownership

User model preference: **Sol (`gpt-6-sol`) for every subagent**, including research, implementation, and independent review. Select it explicitly at launch; use a self-contained brief when full-history forks cannot accept model overrides. Do not silently substitute another model.

Current environment supports the root plus three concurrent subagents. Recheck capacity on launch; reserve root for integration. Do not create separate user-facing chats unless requested. Preparation used three read-only workers and did not start implementation.

First recommended dispatch: **ENV-01, AUTH-01, HELPER-01**. ENV-01 owns global Python test/configuration files, so AUTH-01 uses task-specific test modules and waits for ENV-01's verified environment before final full-suite acceptance. As slots free, launch **KO-01**, **INGEST-01**, and **WEB-01** where ownership permits. Build preparation and contract packages can then run alongside backend fixes. The package ledger records dependencies, not a promise to run every row at once.

Protected existing work: main has untracked audit/state documents; `Epilogue-secondary` has staged Android settings, `CLAUDE.md`, and deployment-example changes. No worker may absorb, reset, or publish these incidentally. Before creating worktrees, root must make this backlog and relevant audit context available through explicit prompt copies or a separate reviewed documentation commit; untracked files are not automatically copied.

## Verification conventions

**B** — disposable Python 3.12 environment initially matching the audited test runtime; ENV-01 establishes the reproducible command. Run `python -m pytest -q <named/new modules>` from `ghostwriter/`, and the relevant full backend suite before acceptance. Disable `.env`, use temporary storage, mock DNS/providers/integrations, and prohibit outbound provider calls. Existing audit result is 243 passed/1 DNS failure with that test passing separately under a mock; it is not a new green baseline.

**W** — from `ghostwriter/frontend/`: `npm ci`, `npm run check`, `npm run build`, and targeted/full `npm run test:e2e` after installing the pinned Playwright Chromium. Use fixture APIs. Capture sanitized browser evidence for changed UI behavior. Compiler success alone is insufficient.

**A** — `./gradlew :app:testDebugUnitTest :shared:testDebugUnitTest --no-daemon`, plus relevant instrumented persistence/worker tests when plain JVM tests cannot exercise the failure boundary. BUILD-NATIVE establishes SDK/JDK/Gradle availability; the audit ran zero native tests due to uncached AGP. Do not upgrade toolchains simply to evade setup work.

**I** — load applicable Tuist/XcodeBuildMCP and Swift skills, build KMP XCFramework, regenerate Tuist, discover schemes/simulator destinations, then run the selected module/App tests and simulator build using the real generated workspace. BUILD-NATIVE records exact runnable commands. The existing stale workspace failure is not proof of a current-source compile defect. No signing, device, or live background-timing claims from simulator tests.

All PRs: `git diff --check`, focused behavior/failure tests, inspected final diff, independent review for significant behavioral/security/data changes, and command/result/limitations in the unique evidence file. Only broaden tests when changed dependencies or unresolved concerns warrant it.

## Package ledger

Execution is in final review and integration. Current owners, exact worktrees/bases, verification and PR URLs are authoritative in `docs/project-state.md`; the [PR index](results/PR-INDEX.md) lists the published work. The table below is the original scope/dependency map, not live completion status. All 29 original package outcomes are published; review corrections remain explicitly tracked until final combined verification. Result path convention: `docs/work-packages/results/ID.md` on the relevant branch.

| ID | Priority/type | Outcome | Start condition |
|---|---|---|---|
| [AUTH-01](backend.md#auth-01) | P1 | Authentication limits and connection cleanup | Ready; ENV-01 before final suite |
| [HELPER-01](web.md#helper-01) | P1 | Keep helper credentials within their origin | Ready |
| [KO-01](web.md#ko-01) | P1 | Protect unrelated e-books; repair settings dialog | Ready; provision Lua for checks |
| [INGEST-01](backend.md#ingest-01) | P1 | Source-only editions and effective Wallabag mode | Ready; ENV-01 before final suite |
| [ENV-01](backend.md#env-01) | Enabler | Consistent Python installs and isolated tests | Ready; sole global fixture/dependency owner |
| [FETCH-01](backend.md#fetch-01) | P2/security | Validate outbound redirect targets and DNS errors | Ready; preserve private-host opt-in |
| [INPUT-01](backend.md#input-01) | P2 | Intentional validation errors in sync APIs | After ENV-01 and FETCH-01; before sync server work |
| [WALLABAG-01](backend.md#wallabag-01) | P2 | Isolate cached tokens by effective credentials | Ready; no bindery edits |
| [MEDIA-01](backend.md#media-01) | P2 | Reproduce and prevent overlapping media runs | Ready; bounded single-process scope |
| [RETENTION-01](backend.md#retention-01) | Design | Define ownership and safe deletion behavior | Ready for contract/evidence PR |
| [RETENTION-02](integration.md#retention-02) | P2 | Remove digest-owned rows/files safely | After RETENTION-01 decision and ENV-01 |
| [RECOVERY-01](backend.md#recovery-01) | Investigation | Fault-inject digest failures and restart | After INGEST-01; evidence/design PR |
| [WEB-01](web.md#web-01) | P2/enabler | Repair browser smoke and run it in CI | Ready; owns browser fixtures/new workflow |
| [WEB-02](web.md#web-02) | P2 | Recover expired web sessions correctly | After WEB-01 |
| [BUILD-NATIVE](mobile.md#build-native) | Enabler | Clean Android/KMP/Tuist build and tests | Ready; prerequisite for native acceptance |
| [CONTRACT-01](mobile.md#contract-01) | Design | Fix sync, deletion, article identity/retry semantics | Ready for contract PR; root resolves material choices |
| [ANDROID-FILES](mobile.md#android-files) | P1 | Unique EPUB files and legacy path ownership | Ready; BUILD-NATIVE for acceptance |
| [ANDROID-OBSERVE](mobile.md#android-observe) | P2 | Observe only current generation within lifecycle | Ready; BUILD-NATIVE for acceptance |
| [SYNC-EDITS](mobile.md#sync-edits) | P1 epic | Preserve newer server/device feed edits | After CONTRACT-01 + INPUT-01 + BUILD-NATIVE; four staged PRs |
| [SYNC-DELETE](mobile.md#sync-delete) | P2 epic | Persist offline deletions through restart | After SYNC-EDITS; core/Android/iOS PR stages |
| [ANDROID-DELIVERY](mobile.md#android-delivery) | P1 | Commit article delivery only with durable output | After CONTRACT-01, ANDROID-FILES, SYNC-DELETE, BUILD-NATIVE |
| [ANDROID-FILTER](mobile.md#android-filter) | P3 | Separate promotional rejection from AI errors | After ANDROID-DELIVERY |
| [IOS-SYNC-STATUS](mobile.md#ios-sync-status) | P2 | Report partial sync and preserve pending writes | After SYNC-DELETE + BUILD-NATIVE |
| [IOS-DELIVERY](mobile.md#ios-delivery) | P1/P2 | Deduplicate local editions; expose ingestion errors | After CONTRACT-01 + SYNC-DELETE + BUILD-NATIVE |
| [IOS-RECOVERY](mobile.md#ios-recovery) | P2 | Recover abandoned local digest runs | After IOS-DELIVERY |
| [RUNTIME-01](integration.md#runtime-01) | P2 | Control Docker build inputs/supported runtimes | After ENV-01 |
| [CI-01](integration.md#ci-01) | P2 | Run backend/podcast/helper/plugin regressions | After ENV-01, RUNTIME-01, AUTH-01, HELPER-01, KO-01 |
| [JOURNEY-01](integration.md#journey-01) | Verification | Local reading/listening integration with mock providers | After ENV-01, AUTH-01, INGEST-01, RETENTION-02, WEB-01/02 and runtime fixes |
| [RELEASE-01](web.md#release-01) | Verification | Synthetic migration/backup/restore readiness | After relevant fixes/runtime; no release or deploy |

**Held:** [DEPLOY-01](web.md#deploy-01), repair of ignored personal deployment infrastructure. RELEASE-01 documents the gap; publishing a sanitized generic helper is a separate scope decision.

SYNC-EDITS and SYNC-DELETE are coordination epics with explicit PR stages, not single unrestricted assignments. CONTRACT-01 must produce the frozen DTO/schema/error examples and exact stage ownership before root dispatches those stages. No other row authorizes a broad cross-platform rewrite.


## Work packages

Full launch-ready briefs are grouped by ownership area:

- [Backend packages](backend.md): auth, ingestion, test environment, fetching, validation, retention design, Wallabag cache, recovery and media concurrency.
- [Native/shared packages](mobile.md): toolchain, contracts, Android artifact/delivery fixes, staged sync/deletion, iOS truthfulness/dedup/recovery, Android observation/filtering.
- [Web/integrations packages](web.md): helper, KOReader, browser checks, web sessions, release readiness and held deployment work.
- [Integration packages](integration.md): retention implementation, runtime inputs, CI coverage, fixture end-to-end journey.

For every launch, root fills the [worker prompt](worker-prompt.md), including exact worktree/base and dependencies. A named package plus the inherited execution agreement is the complete assignment; do not dispatch a title alone.

### Audit coverage

R01/R02 → AUTH-01; R03 → KO-01; R04 → CONTRACT-01/SYNC-EDITS; R05 → INGEST-01; R06 → ANDROID-DELIVERY/IOS-DELIVERY; R07 → SYNC-DELETE; R08 → RETENTION-01/02; R09 → HELPER-01; R10 → ENV-01/WEB-01/BUILD-NATIVE/CI-01/JOURNEY-01; R11 → ANDROID-FILES.

Mobile M6/M7/M8/M9 → IOS-SYNC-STATUS/ANDROID-OBSERVE/IOS-RECOVERY/ANDROID-FILTER. Backend appendix mode/cache/fetch/DNS/UUID/concurrency/recovery/dependency findings → INGEST-01/WALLABAG-01/FETCH-01/INPUT-01/MEDIA-01/RECOVERY-01/ENV-01. Web appendix dialog/session/runtime/deployment/readiness findings → KO-01/WEB-02/RUNTIME-01/DEPLOY-01/RELEASE-01. Architecture observations and product expansion are deliberately deferred, not silently treated as resolved.


## Product choices kept outside the reliability backlog

Audience/tenancy expansion, Android's new-install Ghostwriter release flag, generated-podcast native UI/playback, one-off creation in the browser, naming/positioning, provider changes, guaranteed scheduling, and a distributed queue remain product choices. No package silently enables these features or promises complete platform parity. The contract package identifies decisions necessary for reliability work and presents concrete defaults/tradeoffs to root; root only asks the user when the choice materially changes product behavior.

## Launch command in conversation

“Start the first wave from `docs/work-packages/backlog.md`; manage workers, verify their output, and have them create PRs.”

Root can then dispatch without further permission for ordinary edits/tests/branch pushes/PR creation within the packages. Later waves follow dependency readiness. No recurring automation or unattended future wake-up is configured by this document.

## Preparation review

2026-09-27: three read-only component workers revalidated affected source and prepared briefs. A subsequent independent **Sol** reviewer inspected backlog coverage, dependencies, ownership, policy gates, and authorization boundaries and reported no actionable findings. Relative document links/anchors and whitespace were checked locally. These checks validate the plan; no product test, implementation, build, PR, merge, or deployment occurred during preparation. Earlier component workers completed before the user specified Sol; all future subagents use the recorded preference.

## Confirmed contract direction (user, 2026-09-27)

- Feed conflicts preserve newer server state and retain local pending edits for explicit resolution.
- Normal native editions deliver an article once; delivery identity survives history deletion; explicit regeneration is separate.
- Episode-referenced digests are retained: block manual deletion and skip automatic deletion while referenced. Unknown historical orphan files remain untouched.

The contract packages subsequently defined compatibility, persistence and recovery behavior before dependent implementation; their current contract and result documents record the accepted details. Full-backlog execution is authorized; merging/deployment remain excluded.

### Historical first-wave checkpoint — 2026-09-27

At this historical checkpoint, ENV#75, AUTH#76, HELPER#74 and INGEST#77 were published with clean independent Sol reviews and relevant passing checks. INGEST stacks on ENV. WEB#78 is draft pending reviewed Linux visual baselines and final Sol review. KO ownership corrections and BUILD-NATIVE hosted checks remain active. CONTRACT-01 exact design at `codex/contract-01-sync-delivery:d07b4d4` is under review; dependent implementation is not yet dispatched. Root `docs/project-state.md` is the live ledger.
