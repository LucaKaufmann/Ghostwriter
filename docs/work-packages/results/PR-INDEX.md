# Pull request index

Checkpoint: 2026-09-27. All29 original package outcomes are published. Review follow-ups and aggregate verification remain active; see [project state](../../project-state.md) and [review dispositions](PR-REVIEW-FOLLOWUP.md). Eleven PRs were merged externally, including three into prerequisite branches. The orchestrator has not merged or deployed.

| PR | Outcome | State / base |
|---|---|---|
| [#74](https://github.com/LucaKaufmann/Ghostwriter/pull/74) | fix: bind podcast helper credentials to the configured origin | Merged externally; `main` |
| [#75](https://github.com/LucaKaufmann/Ghostwriter/pull/75) | test: make Ghostwriter backend installs and tests hermetic | Merged externally; `main` |
| [#76](https://github.com/LucaKaufmann/Ghostwriter/pull/76) | fix: enforce auth throttling and release request sessions | Merged externally; `codex/env-01-hermetic-tests` |
| [#77](https://github.com/LucaKaufmann/Ghostwriter/pull/77) | fix: generate digests from enabled non-RSS sources | Merged externally; `codex/env-01-hermetic-tests` |
| [#78](https://github.com/LucaKaufmann/Ghostwriter/pull/78) | test: run current Ghostwriter browser smoke flows in CI | Merged externally; `main` |
| [#79](https://github.com/LucaKaufmann/Ghostwriter/pull/79) | build: verify native toolchains and simulator tests | Merged externally; `main` |
| [#80](https://github.com/LucaKaufmann/Ghostwriter/pull/80) | docs: preserve reliability backlog and project checkpoints | Merged externally; `main` |
| [#81](https://github.com/LucaKaufmann/Ghostwriter/pull/81) | docs: define safe digest retention and retry behavior | Merged externally; `codex/env-01-hermetic-tests` |
| [#82](https://github.com/LucaKaufmann/Ghostwriter/pull/82) | docs: define feed sync and native delivery contracts | Merged externally; `main` |
| [#83](https://github.com/LucaKaufmann/Ghostwriter/pull/83) | fix: control Ghostwriter container build inputs | Open; `codex/env-01-hermetic-tests` |
| [#84](https://github.com/LucaKaufmann/Ghostwriter/pull/84) | fix: isolate Wallabag tokens by service configuration | Open; `codex/ingest-01-source-editions` |
| [#85](https://github.com/LucaKaufmann/Ghostwriter/pull/85) | fix: preserve Android digest artifacts through their lifecycle | Open; `codex/build-native-baseline` |
| [#86](https://github.com/LucaKaufmann/Ghostwriter/pull/86) | fix: recover expired web sessions and discard stale downloads | Merged externally; `main` |
| [#87](https://github.com/LucaKaufmann/Ghostwriter/pull/87) | fix: restrict KOReader cleanup to verified owned downloads | Merged externally; `main` |
| [#88](https://github.com/LucaKaufmann/Ghostwriter/pull/88) | ci: run Ghostwriter backend helper and plugin regressions | Open; `codex/ci-01-verified-base` |
| [#89](https://github.com/LucaKaufmann/Ghostwriter/pull/89) | fix: bind Android generation observation to the current work | Open; `codex/android-files-unique-artifacts` |
| [#90](https://github.com/LucaKaufmann/Ghostwriter/pull/90) | fix: bound and validate feed and article fetches | Open; `codex/env-01-hermetic-tests` |
| [#91](https://github.com/LucaKaufmann/Ghostwriter/pull/91) | fix: serialize media runs and clean cancelled processing | Open; `codex/env-01-hermetic-tests` |
| [#92](https://github.com/LucaKaufmann/Ghostwriter/pull/92) | test: characterize digest publication and recovery boundaries | Open; `codex/ingest-01-source-editions` |
| [#93](https://github.com/LucaKaufmann/Ghostwriter/pull/93) | fix: delete digest-owned data safely and preserve referenced editions | Open; `codex/retention-01-deletion-contract` |
| [#94](https://github.com/LucaKaufmann/Ghostwriter/pull/94) | fix: validate sync UUIDs and feed URLs before writes | Open; `codex/fetch-01-bounded-requests` |
| [#95](https://github.com/LucaKaufmann/Ghostwriter/pull/95) | test: verify the live reading and listening journey | Open; `codex/sync-server-verified-base` |
| [#96](https://github.com/LucaKaufmann/Ghostwriter/pull/96) | fix: guard feed sync with versions and durable receipts | Open; `codex/sync-server-verified-base` |
| [#97](https://github.com/LucaKaufmann/Ghostwriter/pull/97) | fix: publish digests before acknowledging source items | Open; `codex/sync-edits-server` |
| [#98](https://github.com/LucaKaufmann/Ghostwriter/pull/98) | test: verify migration and stopped-backup restore readiness | Open; `codex/release-01-verified-base` |
| [#99](https://github.com/LucaKaufmann/Ghostwriter/pull/99) | feat: add versioned shared feed sync orchestration | Open; `codex/sync-edits-server` |
| [#100](https://github.com/LucaKaufmann/Ghostwriter/pull/100) | feat: share stable article delivery identities across native clients | Open; `codex/sync-edits-kmp` |
| [#101](https://github.com/LucaKaufmann/Ghostwriter/pull/101) | test: verify shared feed protocol against a live backend fixture | Open; `codex/sync-live-verified-base` |
| [#102](https://github.com/LucaKaufmann/Ghostwriter/pull/102) | feat: preserve Android feed edits and deletions through sync | Open; `codex/delivery-identity-core` |
| [#103](https://github.com/LucaKaufmann/Ghostwriter/pull/103) | feat: preserve iOS feed edits and deletions through sync | Open; `codex/delivery-identity-core` |
| [#104](https://github.com/LucaKaufmann/Ghostwriter/pull/104) | fix: commit Android article delivery with durable editions | Open; `codex/sync-edits-android` |
| [#105](https://github.com/LucaKaufmann/Ghostwriter/pull/105) | fix: report iOS sync outcomes and preserve partial progress | Open; `codex/sync-edits-ios` |
| [#106](https://github.com/LucaKaufmann/Ghostwriter/pull/106) | docs: refresh project continuity and review follow-up ledger | Open; `main` |
| [#107](https://github.com/LucaKaufmann/Ghostwriter/pull/107) | feat: deliver local iOS editions once with durable outcomes | Open; `codex/sync-edits-ios` |
| [#108](https://github.com/LucaKaufmann/Ghostwriter/pull/108) | fix: cap combined editions and preserve deletion ownership | Open; `codex/review-fixes-verified-base` |
| [#109](https://github.com/LucaKaufmann/Ghostwriter/pull/109) | fix: preserve sync semantics during bounded DNS validation | Open; `codex/review-fixes-verified-base` |
| [#110](https://github.com/LucaKaufmann/Ghostwriter/pull/110) | test: strengthen sync contract and restore verification | Open; `codex/review-fixes-verified-base` |
| [#111](https://github.com/LucaKaufmann/Ghostwriter/pull/111) | fix: preserve web feed proposals through restoration conflicts | Open; `codex/review-fixes-verified-base` |
| [#112](https://github.com/LucaKaufmann/Ghostwriter/pull/112) | fix: preserve Android feed proposals and reset integrity | Open; `codex/review-fixes-verified-base` |
| [#113](https://github.com/LucaKaufmann/Ghostwriter/pull/113) | fix: keep feed article caps within native integer bounds | Open; `codex/review-followup-base` |
| [#114](https://github.com/LucaKaufmann/Ghostwriter/pull/114) | fix: retain private digest ownership after episode deletion | Open; `codex/review-followup-base` |
| [#115](https://github.com/LucaKaufmann/Ghostwriter/pull/115) | fix: address reviewed iOS sync follow-ups | Open; `codex/ios-sync-review-verified-base` |
| [#116](https://github.com/LucaKaufmann/Ghostwriter/pull/116) | fix: recover interrupted local iOS generation | Open; `codex/review-followup-base` |
| [#117](https://github.com/LucaKaufmann/Ghostwriter/pull/117) | fix: download one-off podcast audio from configured API | Open; `codex/review-followup-base` |
| [#118](https://github.com/LucaKaufmann/Ghostwriter/pull/118) | fix: cover Android scheduled delivery outcomes | Open; `codex/review-followup-base` |

Only the final aggregate PR remains to be created. Updated corrections to111/112/115/116 remain under verification; see the current state and review ledger.

Native podcast parity, positioning, multi-tenant hosting and DEPLOY-01 remain outside this scope. Provider calls were mocked; no release/production certification is implied.
