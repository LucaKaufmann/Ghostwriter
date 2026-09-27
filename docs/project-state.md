# Project state

Updated 2026-09-28 (Europe/Zurich). Historical audit baseline: `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`. The audit remains a dated snapshot, not a current completion ledger.

## Outcome and authority

**All 29 approved reliability packages are complete, merged and verified.** All 11 headline audit findings have remedies. Original PRs 74–119 and late iOS review fixes 120–121 are merged. Verified product source on main is `c894fb8072c3919f367722782dbde25b12b6760c`; the final closeout checkpoint changes documentation only.

The user authorized implementation, PRs, review corrections, merging all scoped work and verification on main. All workers/reviewers use Sol (`gpt-6-sol`). No release, deployment, tag, branch deletion, production-content inspection or paid-provider invocation occurred. No recurring automation exists.

The [merge plan](work-packages/merge-plan.md), [PR index](work-packages/results/PR-INDEX.md), [review dispositions](work-packages/results/PR-REVIEW-FOLLOWUP.md) and [main verification report](work-packages/results/MAIN-MERGE-VERIFICATION.md) contain the durable evidence. Historical task checkboxes do not reopen completed work.

## Confirmed product decisions

- Newer server feed state wins conflicts; retain the device's local proposal for explicit resolution.
- Normal native editions deliver once across history/EPUB deletion. Explicit regeneration may repeat content; recovery never silently regenerates a lost artifact.
- Podcast references block manual digest deletion and cause scheduled cleanup to skip that digest. Unknown historical orphan files remain untouched.
- Feeds/configuration/digests remain largely installation-wide; podcast ownership is more granular. This work does not establish tenant isolation or complete native podcast parity.

## Task ledger

| Task | Owner / status | Accepted result |
|---|---|---|
| Reliability implementation | Root and Sol workers; complete | All 29 packages and accepted review corrections integrated. Immutable per-package evidence is linked in the PR index. |
| Dependency-safe merges | Root; complete, independently checked | Scoped children merged before parents, then continuity106 and aggregate119. Every original scoped head and merge commit is retained in main ancestry. History reconciliation preserved the entire accepted aggregate tree before documentation updates. |
| Main verification | Root; complete | Six workflows on 5c5cc40: 10 successful jobs and one intentional publication skip. Local shared native 62/APK also passed. iOS 197 units plus 2 UI tests passed on 174a349; final three-case UI run passed on c894fb80. Other surfaces are byte-identical across these main revisions. |
| Late iOS review fixes | Sol ios_sync_closeout; complete | PR120 fixes invalid-URL recovery guidance; PR121 handles remaining queued proposals. Both independently reviewed and visually inspected. Store/wire contracts unchanged. |
| Durable closeout | Root; complete | This documentation-only checkpoint records exact evidence and the release checklist through migration 028. No implementation worker remains active. |

Temporary worktrees/evidence: `/private/tmp/epilogue-backlog-20260927/`. Final documentation branch: `codex/reliability-main-closeout`, worktree `main-closeout-docs`, based on verified main c894fb80. Root alone owns shared planning documents.

## Verification and review

Main 5c5cc40 passed all six hosted workflows: 462 backend tests; Android/shared unit checks; iOS framework/App build and 197 workspace units; 40 browser scenarios; frontend check/build; 20 helper tests; KOReader host harness; one real Ktor→FastAPI fixture and one synthetic reading/listening journey; amd64 image build/startup. Image publication was intentionally skipped. Local main verification added 62 Kotlin/Native tests and Android APK assembly.

Main 174a349 passed197 iOS workspace units and 2 focused UI tests. The subsequent text/accessibility/fixture-only correction passed all 3 focused UI cases on exact main c894fb80, with no failures/skips and clean tracked state. The197-unit suite was not repeatedly rerun for that final UI-only delta. Source comparisons verify unchanged backend, web, shared, Android, models and sync stores; see the main report for precise provenance.

All original 46 PRs were swept at 2026-09-27T22:13:24Z: 114 inline comments, 61 review bodies, 47 issue comments. Subsequent119/120/121 refreshes and dispositions are recorded in the review ledger. Accepted late findings: 106 stale status text;103 invalid-URL title-only correction;120 queued-successor guidance. The90 DNS-blocking allegation was obsolete against the async bounded validator. Earlier missing-evidence claims were disproved by 46/46 exact GitHub Contents API checks. No external review reply or thread-resolution claim.

Existing non-failing Swift/Kotlin/SDK warnings and CoreData model-checksum diagnostics remain visible in logs. Historical SQL fixture whitespace is preserved. Fixtures mock external generation and use synthetic content/audio. No physical-device background timing, real audio quality, KOReader hardware, arm64 container runtime, signing/distribution or production-restore claim. Generation gates are process-local; the isolated WorkManager 2.9 period-count adapter needs rechecking on dependency upgrades.

## Schema and operational boundaries

Alembic **026→027→028**: feed versions/receipts/instance identity, source acknowledgements, durable one-off ownership. Room **8→9→10→11**: feed outbox, delivery claims, scheduled occurrence coverage. Frozen SwiftData **V1→V2→V3**: feed sync and delivery. Root allocates revisions; the late UI fixes add no schema changes.

A future rollout must back up first, migrate the server before enabling native v2 sync, and avoid running an old server binary over a v2 database. After restoring a backup, migrate and rotate sync identity before serving; explicitly reconcile devices. See [release instructions](../ghostwriter/RELEASE.md).

## Exact next action and open decisions

No reliability implementation or required verification remains. Choose the next bounded product/release outcome with the user. Audience, preferred reading/listening/native surface, release target, generated-podcast native UI, durable native configuration outbox, distributed scheduling and personal deployment helper DEPLOY-01 remain outside this scope. Do not deploy or restart old packages without a new outcome.

Protected work remains intact: original `/Users/luca/git/Epilogue` stays on main cdb776d with local audit/planning files; `/Users/luca/git/Epilogue-secondary` stays on gitbutler/workspace14a753e with staged CLAUDE.md, Android SettingsScreen.kt and deployment-example changes. Do not absorb, reset or publish those changes.
