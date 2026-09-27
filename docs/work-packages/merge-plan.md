# Reliability PR merge plan

Authorized by the user on2026-09-28 (Europe/Zurich): merge all reliability PRs, verify actual main, and provide a detailed change summary. This does not authorize a release, tag, deployment or real provider invocation.

## Why this order

The final aggregate PR119 contains the reviewed changes and later fixes through cherry-picks. Scoped PRs still point at prerequisite or frozen integration branches. Merge children into their existing bases before merging parents; otherwise a parent PR can finish before its child's commits are incorporated. Keep main's product code stable until the reviewed aggregate lands. PR106's12changed documentation files are byte-identical to their versions in aggregate3c60540, so its main merge precedes119 safely.

## Ordered merge queue

PR74–88 are already merged externally and will not be merged again. The remaining31PRs use GitHub merge commits, pinned to freshly read head SHAs; preserve branches and stop/replan on an unexpected change or conflict.

| Order | PR | Existing base |
|---|---|---|
| 1 | [#89](https://github.com/LucaKaufmann/Ghostwriter/pull/89) | `codex/android-files-unique-artifacts` |
| 2 | [#94](https://github.com/LucaKaufmann/Ghostwriter/pull/94) | `codex/fetch-01-bounded-requests` |
| 3 | [#90](https://github.com/LucaKaufmann/Ghostwriter/pull/90) | `codex/env-01-hermetic-tests` |
| 4 | [#91](https://github.com/LucaKaufmann/Ghostwriter/pull/91) | `codex/env-01-hermetic-tests` |
| 5 | [#92](https://github.com/LucaKaufmann/Ghostwriter/pull/92) | `codex/ingest-01-source-editions` |
| 6 | [#93](https://github.com/LucaKaufmann/Ghostwriter/pull/93) | `codex/retention-01-deletion-contract` |
| 7 | [#95](https://github.com/LucaKaufmann/Ghostwriter/pull/95) | `codex/sync-server-verified-base` |
| 8 | [#97](https://github.com/LucaKaufmann/Ghostwriter/pull/97) | `codex/sync-edits-server` |
| 9 | [#101](https://github.com/LucaKaufmann/Ghostwriter/pull/101) | `codex/sync-live-verified-base` |
| 10 | [#98](https://github.com/LucaKaufmann/Ghostwriter/pull/98) | `codex/release-01-verified-base` |
| 11 | [#104](https://github.com/LucaKaufmann/Ghostwriter/pull/104) | `codex/sync-edits-android` |
| 12 | [#105](https://github.com/LucaKaufmann/Ghostwriter/pull/105) | `codex/sync-edits-ios` |
| 13 | [#107](https://github.com/LucaKaufmann/Ghostwriter/pull/107) | `codex/sync-edits-ios` |
| 14 | [#102](https://github.com/LucaKaufmann/Ghostwriter/pull/102) | `codex/delivery-identity-core` |
| 15 | [#103](https://github.com/LucaKaufmann/Ghostwriter/pull/103) | `codex/delivery-identity-core` |
| 16 | [#100](https://github.com/LucaKaufmann/Ghostwriter/pull/100) | `codex/sync-edits-kmp` |
| 17 | [#99](https://github.com/LucaKaufmann/Ghostwriter/pull/99) | `codex/sync-edits-server` |
| 18 | [#96](https://github.com/LucaKaufmann/Ghostwriter/pull/96) | `codex/sync-server-verified-base` |
| 19 | [#108](https://github.com/LucaKaufmann/Ghostwriter/pull/108) | `codex/review-fixes-verified-base` |
| 20 | [#109](https://github.com/LucaKaufmann/Ghostwriter/pull/109) | `codex/review-fixes-verified-base` |
| 21 | [#110](https://github.com/LucaKaufmann/Ghostwriter/pull/110) | `codex/review-fixes-verified-base` |
| 22 | [#111](https://github.com/LucaKaufmann/Ghostwriter/pull/111) | `codex/review-fixes-verified-base` |
| 23 | [#112](https://github.com/LucaKaufmann/Ghostwriter/pull/112) | `codex/review-fixes-verified-base` |
| 24 | [#113](https://github.com/LucaKaufmann/Ghostwriter/pull/113) | `codex/review-followup-base` |
| 25 | [#114](https://github.com/LucaKaufmann/Ghostwriter/pull/114) | `codex/review-followup-base` |
| 26 | [#115](https://github.com/LucaKaufmann/Ghostwriter/pull/115) | `codex/ios-sync-review-verified-base` |
| 27 | [#116](https://github.com/LucaKaufmann/Ghostwriter/pull/116) | `codex/review-followup-base` |
| 28 | [#117](https://github.com/LucaKaufmann/Ghostwriter/pull/117) | `codex/review-followup-base` |
| 29 | [#118](https://github.com/LucaKaufmann/Ghostwriter/pull/118) | `codex/review-followup-base` |
| 30 | [#106](https://github.com/LucaKaufmann/Ghostwriter/pull/106) | `main` |
| 31 | [#119](https://github.com/LucaKaufmann/Ghostwriter/pull/119) | `main` |

## Integration and preservation checks

1. Snapshot every original head/base, review feedback and CI; inspect new actionable findings. Existing rulesets are empty and main is unprotected, but do not bypass policies or force-push.
2. Merge scoped PRs into their existing bases in the queue above. A parent head may advance after its children merge; re-read and record the exact current head and resulting merge commit for each action.
3. Reconcile those already-incorporated histories into the aggregate while retaining its reviewed tree. Inspect missing added files and unique differences first. History-only merge resolutions must be explicit: original behavior was cherry-picked and superseded by reviewed fixes, so old snapshots must not overwrite it. Record each resulting scoped merge commit as an ancestor; verify complete aggregate tree equality to the frozen acceptance tree before adding merge-plan/status documentation.
4. Merge106, then reconcile main's ancestry and root-owned merge documents in119. Verify the final119product tree against accepted3c60540, all scoped histories reachable, and current main changes accounted for. Merge119 with a normal merge commit, never squash away reconciled ancestry.
5. Verify all46PRs report MERGED, remote main contains all recorded merge commits, and its tree matches the reviewed final aggregate. Preserve original and secondary worktrees.

## Verification on main

Use a fresh isolated checkout of the exact remote main SHA. Dispatch the six existing workflows explicitly on main and verify their run SHAs: backend/helper/KOReader/frontend; browser behavior/visuals; live Ktor→FastAPI; synthetic reading/listening journey; native builds/unit tests; image build/health smoke. The image workflow publishes only on version tags, so main dispatch validates without publishing. Also run local shared Kotlin/Native tests and Android APK assembly on main to cover gates not present in the hosted jobs. No redundant full-suite reruns without a source change/failure.

Done means all PR states and commit ancestry are accounted for, main checks pass with exact command/run evidence, final documentation records actual results, and the detailed summary explains behavior/platform/migration changes and remaining limits. CI success is not physical-device, real-audio-provider or production-restore validation.

Status at 2026-09-27T22:10Z: all 30 scoped merges in the queue completed; all 45 scoped PRs74–118 report merged. Every original head and merge commit is an ancestor of reconciled aggregate `6c8ab205cd350b4c3c90885f53447e3435fcf9c2`. Its entire tree equals accepted `3c60540a9d11b3ae277818f834b42272607290fe` (tree `b651aa87dbee79d26cdd2e1547ffe7ded3be0505`). This also retains original heads previously squash-merged externally. PR119 subsequently merged at main5c5cc40 and all six main workflows passed. Local ledger: `/private/tmp/epilogue-backlog-20260927/merge-closeout/`.


## Late review follow-up

After the original queue, the final review sweep found an iOS rejected-URL resolution UX issue. The bounded fix was independently reviewed, tested through the simulator UI and visually inspected, then merged as [PR120](https://github.com/LucaKaufmann/Ghostwriter/pull/120) after119. Main174a349 exactly equals accepted PR120 head29dca9b. Only four iOS App files and its evidence changed; backend, web, shared and Android files remain identical to main5c5cc40. The affected iOS surface passed197 workspace unit tests and2 focused UI tests on174a349. The final documentation and test-fixture checkpoint records that completed acceptance. The original ordered queue and its evidence remain historical.

Final verification: all required checks passed; no active implementation workers or unresolved accepted review findings. See [the main verification report](results/MAIN-MERGE-VERIFICATION.md).

The final queued-successor guidance correction followed as [PR121](https://github.com/LucaKaufmann/Ghostwriter/pull/121), merged into mainc894fb80 after independent review and UI evidence. All three focused UI cases passed on that exact main revision before the documentation and test-fixture checkpoint.

## Final verified endpoint

PR122 merged at main68a797ed497310a836c854294edd65ca7327cf88. All49 PRs74–122 report merged and their original heads/merge commits are retained. The final fixture case passed1/1 on that exact main, with a clean tracked checkout. This evidence-only closeout records the completed result; no further implementation or required test remains.
