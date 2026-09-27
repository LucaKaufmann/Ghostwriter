# Reliability backlog: merged main verification

Checkpoint: 2026-09-28 (Europe/Zurich). Verification complete. [PR122](https://github.com/LucaKaufmann/Ghostwriter/pull/122) records the final documentation and test-fixture checkpoint, preserving verified production behavior.

## Scope and merge result

The 29 approved reliability packages and the previously accepted review corrections are integrated through all 46 PRs **#74–#119**. Late review found two iOS rejection-guidance issues, fixed in merged PR120 and PR121. Their actual-main verification is recorded separately below. GitHub reports all 46 merged. The final integration merge is `5c5cc4037f5d9bfccd6e04bb19addca2ff914d03` on main, created at 2026-09-27T22:10:44Z.

The [merge plan](../merge-plan.md) lists the exact child-before-parent order. Scoped PRs merged into their existing prerequisite bases; continuity PR106 preceded aggregate PR119 on main. The accepted aggregate already contained their changes and later fixes through cherry-picks. Explicit history-only merge resolutions retained those original histories without reintroducing superseded code. Every original head and scoped merge commit was proven an ancestor of final main. Before documentation updates, the entire reconciled tree exactly equaled accepted `3c60540a9d11b3ae277818f834b42272607290fe` (tree `b651aa87dbee79d26cdd2e1547ffe7ded3be0505`). Main's tree exactly equals final PR119 head `7070e45436f23dcd3f63cde7a8360c001a999e07`; production and test files are unchanged from the accepted aggregate.

No force push, branch deletion, policy bypass, release, deployment, production-content access or paid-provider invocation occurred. Original and secondary checkouts were preserved. Verification uses a separate detached checkout of exact main.

## Actual-main checks

All six workflows were explicitly dispatched on `main`, and each run's `headSha` was checked against `5c5cc4037f5d9bfccd6e04bb19addca2ff914d03`. All six workflows completed successfully: 10 successful jobs and one intentional image-publication skip, verified at 2026-09-27T22:33:43Z. The image workflow's publish job is restricted to version tags; main validation does not publish an image.

| Check | Actual-main evidence | Result |
|---|---|---|
| Backend, helper, KOReader, frontend | [Run 36354405642](https://github.com/LucaKaufmann/Ghostwriter/actions/runs/36354405642) | Passed |
| Browser behavior and visuals | [Run 36354407236](https://github.com/LucaKaufmann/Ghostwriter/actions/runs/36354407236) | Passed |
| Real Ktor→FastAPI contract | [Run 36354409259](https://github.com/LucaKaufmann/Ghostwriter/actions/runs/36354409259) | Passed |
| Synthetic reading/listening journey | [Run 36354411064](https://github.com/LucaKaufmann/Ghostwriter/actions/runs/36354411064) | Passed |
| Android/shared tests, iOS app/framework and workspace tests | [Run 36354412804](https://github.com/LucaKaufmann/Ghostwriter/actions/runs/36354412804) | Passed: Android/shared unit gate; iOS framework/App build; 197 workspace unit tests |
| amd64 image build and startup health | [Run 36354414536](https://github.com/LucaKaufmann/Ghostwriter/actions/runs/36354414536) | Passed; publication skipped |
| Supplementary local shared Kotlin/Native tests and Android APK | Exact main checkout; JDK17, SDK35; `./gradlew :shared:iosSimulatorArm64Test :app:assembleDebug --offline --no-daemon` | Passed: 62 tests, zero skips/failures; APK built |

Earlier accepted source `3c60540` completed every hosted check successfully, with only image publication intentionally skipped. Ten superseded PR runs (two for the history/documentation-only head `7070e45`, eight for merged stack branches) were deliberately canceled in favor of the main runs above; these cancellations are not main failures. The redundant PR120 native run was also canceled after its exact-main197-unit/2-UI verification passed.

## Late iOS review correction

[PR120](https://github.com/LucaKaufmann/Ghostwriter/pull/120) merged at main `174a349cb145342ce129249762b458334851eae8`, whose entire tree equals accepted PR head `29dca9b78e6606dd20e657f89ec44a20b6c4b15d`. An `invalid_url` rejection now explains discard/re-add and hides ineffective title-only correction. Other rejected edits and deletes retain their behavior. A guarded isolated settings fixture makes the actual discard-and-add UI flow deterministic.

Source `548a817` passed independent Sol review, two focused UI tests, the simulator build and an additional screenshot capture run. Root inspected the [rendered screen](assets/ios-invalid-url/rejected-invalid-url.png). The initial test exposed a missing fixture destination; that was fixed without changing production settings, and the final flow passed. Backend/web/shared/Android files are byte-identical to verified main5c5cc40. Final checks on exact main `174a349`: **197/197 workspace unit tests and 2/2 focused UI tests passed**, with no failures or skips; tracked checkout clean. Commands used `xcodebuildmcp simulator test`, scheme `Epilogue-Workspace`, iPhone 16 Plus/iOS18.6. The unit run excluded the UI target; the separate UI run selected the two feed-resolution cases. Logs: `actual-main-ios-workspace-unit.log` and `actual-main-ios-focused-ui.log`; machine-readable record: `merge-closeout/actual-main-ios.json`. Existing non-failing CoreData model-checksum diagnostics remain visible in the unit log.

[PR121](https://github.com/LucaKaufmann/Ghostwriter/pull/121) addresses the subsequent queued-successor review: guidance now distinguishes discarding one proposal from resolving later proposals for the same URL. Source `c2f072d9` passed independent review, both interaction flows, the corrected screen assertion and screenshot capture; root inspected both [guidance](assets/ios-invalid-url-successor/rejected-guidance.png) and [remaining-proposal](assets/ios-invalid-url-successor/remaining-proposal.png) screens. The initial screen query hit XCTest's 128-character query limit; a stable accessibility identifier and full-label assertion corrected that test-only failure.

Main `c894fb8072c3919f367722782dbde25b12b6760c` exactly equals accepted PR121 head `b3ad9d9bc2b8bf92e473bb00fb61a042533ffcfe`. Its delta from174a349 is guidance/accessibility text, synthetic fixture and UI tests plus evidence. Store, model, sync, backend, web, shared and Android behavior are unchanged. Final three-case UI check on exact main `c894fb80`: **3/3 passed together, zero failures/skips**, with clean tracked state and matching remote main. Command: `xcodebuildmcp simulator test` on `Epilogue-Workspace`, iPhone16Plus/iOS18.6, selecting the resolution fixture, single-proposal discard/add and queued-successor discard/add tests. Log: `actual-main-ios-successor-focused-ui.log`; compact record: `merge-closeout/actual-main-ios-successor.json`. The197-unit suite was already verified on174a349 and was not needlessly repeated for this UI-only change.

## Final fixture fidelity review

The last [PR121 comment4117345638](https://github.com/LucaKaufmann/Ghostwriter/pull/121#discussion_r4117345638) identified test-data drift, not a production defect. Real queued edits already update the visible feed title immediately. The synthetic chain fixture kept the older title; correction `0b6715fb98e799e648c98d1e123536aa6c37e1d7` now seeds the latest title and asserts it survives Discard before disappearing after Keep removed. The rejected head mutation still retains its original payload.

The two-location fixture/test correction passed independent Sol review and its single affected UI case **1/1**, with no failures/skips. Command: `xcodebuildmcp simulator test`, `Epilogue-Workspace`, iPhone16Plus/iOS18.6, selecting `testInvalidURLSuccessorRequiresKeepRemovedBeforeCorrectedAdd`. Log: `review-ios-invalid-url-fixture-title-ui.log`; compact record: `merge-closeout/ios-invalid-url-fixture-title.json`. The final checkpoint retains this tested commit as an ancestor and changes no production behavior. The post-merge repetition passed **1/1 on exact remote main `68a797ed497310a836c854294edd65ca7327cf88`**, with zero failures/skips and a clean tracked checkout. Log: `final-main-fixture-title-ui.log`; compact record: `merge-closeout/final-main-fixture-title.json`. All49 PRs74–122 were verified merged, every prior PR head/merge commit is an ancestor, and main exactly equals reviewed checkpoint27bb704c. This subsequent evidence-only commit changes no production or test files; source-tree equality is its final verification.

Review cutoff for119/120/121:2026-09-27T22:54:43Z. All three automated reviews completed; every substantive finding is fixed or explicitly dispositioned. Earlier original-PR sweeps remain recorded in the review ledger.

## Audit progress

All 11 headline audit findings R01–R11 have implemented remedies in the approved 29-package reliability plan: authentication/session lifecycle (R01/R02), owned KOReader cleanup (R03), versioned feed conflicts (R04), non-RSS ingestion (R05), durable native delivery (R06), queued deletion (R07), safe backend retention (R08), helper origin confinement (R09), CI coverage (R10), and unique Android artifacts (R11). This is completion of the bounded reliability plan, not a claim that every exploratory recommendation, release requirement or product-parity gap in the broader audit is finished. Both late iOS UX findings are fixed and verified above.

## Delivered behavior

- **Access and source safety:** reachable login/registration throttling; timely database-session closure; helper credentials restricted to the configured origin; bounded fetches, redirects, DNS and decompression; deliberate validation errors before partial batch writes.
- **Ingestion and recovery:** non-RSS-only editions work; Wallabag tokens follow the effective configuration; media subprocess cancellation cleans up processes. Digest completion and delivery state publish together after EPUB finalization, and source acknowledgement retries survive restart.
- **Retention and ownership:** podcast references prevent manual digest deletion and scheduled cleanup; owned rows, EPUBs and PDFs are removed conservatively and retryably. One-off digest privacy persists after episode deletion. KOReader cleanup only deletes verified owned downloads.
- **Feed sync:** versioned server writes, replay receipts and tombstones protect newer server state. Android/iOS persist pending edits and deletes across restart, retain conflicting local proposals, hide pending deletions and guard server changes. KMP validates wire envelopes before native writes; URL admission is strict for new feeds while exact legacy keys/replay remain compatible.
- **Native editions:** shared article identity and durable delivery claims implement deliver-once across history deletion, with explicit regeneration. Android uses unique EPUB files, correct WorkInfo observation and durable scheduled occurrence coverage. iOS persists run outcomes, recovers interruptions, reports partial sync and indexes zero-article remote editions without inventing files.
- **Web:** expired sessions clear only the matching authentication state and discard stale responses/downloads; conflict resolution retains local proposals and edits made while requests are running.
- **Verification and operations:** hermetic backend tests, browser scenarios, native/shared gates, live synthetic journeys, controlled container inputs and migration/backup/restore checks now provide repeatable evidence.

## Schema and rollout implications

Alembic revisions **026→027→028** introduce feed versions/receipts/instance identity, source acknowledgements and durable one-off ownership. SQLite downgrade paths preserve columns/data; new and existing database paths are covered. Android Room evolves **8→9→10→11** for sync outbox, delivery claims and scheduled occurrence coverage. iOS uses frozen SwiftData **V1→V2→V3** schemas for sync and delivery persistence.

For a future deployment: take a stopped backup, upgrade Ghostwriter through Alembic head before enabling native v2 sync, and follow [release instructions](../../../ghostwriter/RELEASE.md). Do not run an older server binary over a v2 database. After restoring a backup, migrate and rotate sync identity before serving, then explicitly reconcile device proposals. This milestone does not deploy anything.

## Remaining limits and next decisions

External providers are mocked and the listening fixture uses synthetic audio. Physical-device background timing, audio quality, KOReader hardware, arm64 container runtime, signing/distribution and production restore remain unverified. Generation gates are process-local. WorkManager 2.9's isolated read-only period-count adapter must be rechecked on dependency upgrades. Feeds/configuration remain installation-wide; this work does not add multi-tenant isolation or complete native podcast parity.

The approved reliability backlog and both late iOS review corrections are complete, merged and verified. Broader audit/product choices remain: primary audience, preferred reading/listening/native surface, release target, durable native configuration outbox, distributed scheduling and the deferred personal deployment helper. The next useful milestone is a deliberately scoped release rehearsal for the chosen surface, including real-device/provider validation where relevant.

## Scoped PR ancestry

All listed merge commits and original heads are ancestors of main `5c5cc40`; original per-package evidence is in the [PR index](PR-INDEX.md).

| PR | Merge commit | Original head at merge |
|---|---|---|
| [#74](https://github.com/LucaKaufmann/Ghostwriter/pull/74) | `0355eb74cff6d4a77a9b997116041091a6317e7f` | `4267ed88d4a3002f9d0325908945a204cbeda799` |
| [#75](https://github.com/LucaKaufmann/Ghostwriter/pull/75) | `4e3868bdb94f3c2b553938cc446f6d8c45cb13e6` | `de68d540ea67383a3843b8085659d29dcf19baaa` |
| [#76](https://github.com/LucaKaufmann/Ghostwriter/pull/76) | `352c00a99b428148ff52bcd880788019b8df1047` | `1da3bb49e4e196f2bf7008a2ffed45da5417f801` |
| [#77](https://github.com/LucaKaufmann/Ghostwriter/pull/77) | `da6f8df14dc8d1088ccd8cfb6225a044e0ab97e8` | `679bd909d5780e55be21d8ea5347e3ea6a9a54d3` |
| [#78](https://github.com/LucaKaufmann/Ghostwriter/pull/78) | `ae56d315cf1cf8e596065ff02ecec3712530f3f1` | `67acec4e0f3607a7c0eedd318c84fd022e55a803` |
| [#79](https://github.com/LucaKaufmann/Ghostwriter/pull/79) | `a8057a276aa43e365cf27e29651ece9e82517d8e` | `8c7c148ab5bc9d59f7305f7b64d0e235e9d60f6f` |
| [#80](https://github.com/LucaKaufmann/Ghostwriter/pull/80) | `fb8279409a92a21b1df83cc6fa6298abe3271403` | `5dd286bd908444946982ca1e3e5052b372eedce8` |
| [#81](https://github.com/LucaKaufmann/Ghostwriter/pull/81) | `b59787998e241260aea01d6966da5c733db017dc` | `7ceada001571a6ad8b7509fb42c03f98c60dd447` |
| [#82](https://github.com/LucaKaufmann/Ghostwriter/pull/82) | `f6b917e2cec13f52720960eab85646fa64bf1c98` | `d11c76608baca43898d6b806429500371d07619c` |
| [#83](https://github.com/LucaKaufmann/Ghostwriter/pull/83) | `863e058ed92b28473ffc1ea4892aee5a4ab58eda` | `6a4f980193faef95a965397db98da844e66700ab` |
| [#84](https://github.com/LucaKaufmann/Ghostwriter/pull/84) | `09c9a36918ad63ae65d3f853682042c42a32b848` | `522bf75858b2c8d04fc1c0d3cfccfacb71744242` |
| [#85](https://github.com/LucaKaufmann/Ghostwriter/pull/85) | `d3e21c191642ff04a591a1be926be6176f09eec0` | `faa3927bdbe34e8836c08850474dcc6e603dc221` |
| [#86](https://github.com/LucaKaufmann/Ghostwriter/pull/86) | `56f0958213758a1ef077ab961a12db7183060a40` | `9d7d12cb25808f08acd577af0239d38d31c18226` |
| [#87](https://github.com/LucaKaufmann/Ghostwriter/pull/87) | `86d3efdaf2506c700b3613dfd0bd9425a05ee8ec` | `620a42676f397cee4dc03aa5c5035e61c0142410` |
| [#88](https://github.com/LucaKaufmann/Ghostwriter/pull/88) | `036bc5297a6a4091c2c19bd1633eca67620d6a04` | `f95ece249fadca6be54584b86a19fc1380269fad` |
| [#89](https://github.com/LucaKaufmann/Ghostwriter/pull/89) | `90dc17b155bed71c5044c612b1d1cdac635c52f0` | `fcf6eab4bcb729dcb32eb77fc851e2a0d662f739` |
| [#90](https://github.com/LucaKaufmann/Ghostwriter/pull/90) | `71674af1aaf1c6ce1a1b911d9f9e48a81d09860c` | `f0e3f67088f28e9bc13725308537ce6ac435d5dc` |
| [#91](https://github.com/LucaKaufmann/Ghostwriter/pull/91) | `aa035fffa702309168f05f73afe0a38a56948371` | `b2265f4e46bd2fc0cc035e47efb4a0b5ad3d9eca` |
| [#92](https://github.com/LucaKaufmann/Ghostwriter/pull/92) | `d88506a7a84bf1d517181995aefcdb660a28e656` | `79de42a55b433a82d3340fe280616c658da7bbda` |
| [#93](https://github.com/LucaKaufmann/Ghostwriter/pull/93) | `9c9f3fe5369db22d9736ff7a42e28a0636a1ccb8` | `99527d2c9726584a627f3a84f26019bd72545e9c` |
| [#94](https://github.com/LucaKaufmann/Ghostwriter/pull/94) | `f0e3f67088f28e9bc13725308537ce6ac435d5dc` | `d40d83b73969c68268489c82e3260cf59781f60f` |
| [#95](https://github.com/LucaKaufmann/Ghostwriter/pull/95) | `097f2e836c94bebc07017023d82b02b36660fcc6` | `2344ec6fc3c6e14dbe03f83088323e6a0f756a61` |
| [#96](https://github.com/LucaKaufmann/Ghostwriter/pull/96) | `ee4e767f8e7171ef5de4b3d3fea042c84dd86846` | `08cbc8e2789fb18e04b3c997aa517d7f427f1680` |
| [#97](https://github.com/LucaKaufmann/Ghostwriter/pull/97) | `5fd4d5d262e8cc666a59c480fc10ff361b13aa53` | `ad67c35f5b2bee39a2bb665818e3485357f32834` |
| [#98](https://github.com/LucaKaufmann/Ghostwriter/pull/98) | `feada80ace0ff4ef621cde3b8b2ff97ed3b8217b` | `13e6f7416f4a8a2a56bc6352188156f1c5cbc000` |
| [#99](https://github.com/LucaKaufmann/Ghostwriter/pull/99) | `08cbc8e2789fb18e04b3c997aa517d7f427f1680` | `80f245d792c0887b9fac4e7e2095f034a6ec84da` |
| [#100](https://github.com/LucaKaufmann/Ghostwriter/pull/100) | `80f245d792c0887b9fac4e7e2095f034a6ec84da` | `f9c2cddc9fce477331945e7f96d506e27c3bc747` |
| [#101](https://github.com/LucaKaufmann/Ghostwriter/pull/101) | `52ce96cba213773ae5a11804d4bfb4c4f609666e` | `43fb1fd4bf1f90ea7cc2c5b118bd2926d8385ae4` |
| [#102](https://github.com/LucaKaufmann/Ghostwriter/pull/102) | `03d1a3ce0e599dfc05fbd6d1f377d4f96db7f015` | `d1a1ea88c1b341c19ebb801a60ce8baf4193bfcf` |
| [#103](https://github.com/LucaKaufmann/Ghostwriter/pull/103) | `f9c2cddc9fce477331945e7f96d506e27c3bc747` | `4800a8dd7d74870cd6a97e57da20b0170d8df5ba` |
| [#104](https://github.com/LucaKaufmann/Ghostwriter/pull/104) | `d1a1ea88c1b341c19ebb801a60ce8baf4193bfcf` | `a070a395b2ab85cfb4826e0d452c826270f95919` |
| [#105](https://github.com/LucaKaufmann/Ghostwriter/pull/105) | `f80779af2fcfb72ce735e86e04a50ed37fc8de3b` | `9c19bc5e3e775c9495be6760af3a49c33fd4af35` |
| [#106](https://github.com/LucaKaufmann/Ghostwriter/pull/106) | `f3eb4b74adf8a97a7db502e5913039f6ec0cdf8b` | `cee5e8a96d3f4229a29410f3b631550fda7f1a61` |
| [#107](https://github.com/LucaKaufmann/Ghostwriter/pull/107) | `4800a8dd7d74870cd6a97e57da20b0170d8df5ba` | `470404d3036ba174a09eca1c494a6b276f1f2ad4` |
| [#108](https://github.com/LucaKaufmann/Ghostwriter/pull/108) | `e02dec2b19aa137d13a6a366431611de3c51b293` | `661637c02b92704cf384192f677f40ebbcb69b53` |
| [#109](https://github.com/LucaKaufmann/Ghostwriter/pull/109) | `796b9155dc94ea6048f20e163002de01c69be196` | `f774ccfe4dce23e65a82a28ea1c5fee4eab45f21` |
| [#110](https://github.com/LucaKaufmann/Ghostwriter/pull/110) | `d7450d855f5eb9c1aff489a2223b52db7314c38e` | `cd2f83effd1d58b6b4a1ef806f3c0d3ae077a209` |
| [#111](https://github.com/LucaKaufmann/Ghostwriter/pull/111) | `f9b379cbf8c5d614cfa82bedb686983e59480904` | `acf7abcbd250cd7c4372558d5b91f4cbc7cba619` |
| [#112](https://github.com/LucaKaufmann/Ghostwriter/pull/112) | `e947248784ac1d70cd13a25ee12165059da66a8a` | `25e2b1dd989e1025db8327a155151d2938c022db` |
| [#113](https://github.com/LucaKaufmann/Ghostwriter/pull/113) | `f197a97969e52cce907396ffec3bf8a46ef44700` | `7871e7afada27cf0a3fc65ffb6f77ad35eac9bbc` |
| [#114](https://github.com/LucaKaufmann/Ghostwriter/pull/114) | `436ec973064c844e1c64aaa478fc9457abcbd61a` | `b92e5b97706f0ee6dc6c50dcc2d2bf9c396681da` |
| [#115](https://github.com/LucaKaufmann/Ghostwriter/pull/115) | `a0a41d6b6d41954ad9e8013dd01d382ba158b9e9` | `c526cb64528ff148006cd6946ea230783f83553c` |
| [#116](https://github.com/LucaKaufmann/Ghostwriter/pull/116) | `ddf638925e089afd86d8f5c6ebda8471a2683f93` | `879f23774d558de9a592c0943e82e5039781ba67` |
| [#117](https://github.com/LucaKaufmann/Ghostwriter/pull/117) | `bab82c59c809bb36d88e6e68a9501e30b4312f37` | `304f9648511e7999168a40886efd3a04e69aed01` |
| [#118](https://github.com/LucaKaufmann/Ghostwriter/pull/118) | `e03f341f42a45eeaf3a399b34c6d0ae9c3c46d6a` | `661cbae82af9a0f1528ee9eec61a868aa77e45f1` |
