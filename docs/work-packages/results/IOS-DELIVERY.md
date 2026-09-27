# IOS-DELIVERY result

Branch: `codex/ios-delivery`, based on accepted feed-sync commit `a2799257b0a9b5b55f66903719d2f2180e0ff1c3`.

The app now makes local editions incrementally. Normal generation claims a valid `(feed URL, normalized article link)` once, retains the claim after history or feed deletion, and records retryable attempts without treating them as delivered. Regeneration is an explicit Settings action; it can include earlier articles while preserving their first-delivery claim. Capped feeds rotate by persisted attempt order, so repeated normal and regeneration runs reach later items. Changed filter settings or feed mode can reconsider a prior exclusion. Fetch, extraction, AI, invalid-link, cancellation, and cap outcomes retain separate diagnostics, including runs with no EPUB. Scheduled empty and deferred outcomes cover the current period; remaining items can enter the next edition or an explicit manual run.

The live store is V3. V1 remains unchanged and V2 is frozen from the accepted feed-sync schema. The production plan now lives in Data and backfills only provable, completed local V2 history with the shared Kotlin article-link identity through a Swift value wrapper in GhostwriterClient, the sole KMP runtime owner. Remote, incomplete, and ambiguous history receives no inferred claim. One unique, fsynced EPUB is written before the final store transaction. History, article associations, delivery ledger, and run outcome commit together; a post-commit error keeps the committed artifact and outcome. Post-commit cleanup reuses the existing 30-digest history and EPUB retention policy without erasing delivery claims.

## Verification

- Shared XCFramework assembly succeeded: `:shared:assembleEpilogueSharedXCFramework --no-daemon` (`/private/tmp/ios-delivery-kmp-build.log`). Tuist install/generate and generic simulator App build passed (`/private/tmp/ios-delivery-build-5.log`).
- Data simulator suite passed **48/48** (`/private/tmp/ios-delivery-correction-data.xcresult`), including captured unversioned V1→V2→V3 and frozen V2→V3 migration/reopen, local-only backfill, independent-context duplicate claim, pre-commit rollback, state-aware exclusion, cap-two fairness over five links, cancellation, partial/empty/deferred/failed outcomes, deletion/regeneration, a post-commit fault, a feed mode change after Fidelity filtering, retention of 30 from 31 generated editions with all 31 claims retained, and injected post-commit retention failure.
- GhostwriterClient golden wrapper suite passed **11/11** (`/private/tmp/ios-delivery-identity.xcresult`). App unit suite passed **33/33** (`/private/tmp/ios-delivery-correction-app.xcresult`). The Domain scheme compiled as an App/Data dependency; its standalone test invocation contained zero tests.
- Simulator UI fixture navigates Settings and renders complete, partial, empty, deferred, and failed diagnostics with the explicit regeneration control (`/private/tmp/ios-delivery-correction-ui.xcresult`). It tests presentation and accessibility, not an actual tap that generates an EPUB; disk-backed Data tests cover generation behavior.
- `git diff --check` passes. No generated project, lockfile, backend, shared, or Android source is included.

The transaction probe established an important SwiftData boundary: an explicit `ModelContext.save()` inside `transaction {}` survives a later throw. The final claim transaction therefore stages all writes and relies on the transaction's commit; injecting a throw before closure exit left no history, associations, delivered claim, or completed run in an independent reopened context. A thrown post-commit fault is tested separately and retains the completed run, claim, history, and artifact. This proves the tested single-process SQLite paths, not cross-process exclusion. The process-wide generation gate and final unique identity/state check cover independent contexts in the app process.

## UI evidence

- [Complete](assets/IOS-DELIVERY/complete.png)
- [Partial with an item error](assets/IOS-DELIVERY/partial.png)
- [Empty](assets/IOS-DELIVERY/empty.png)
- [Deferred after filtering and cap](assets/IOS-DELIVERY/deferred.png)
- [Failed source](assets/IOS-DELIVERY/failed.png)

## Follow-on boundary

The existing scheduler still recognizes a legacy pending Digest as period coverage. The separate IOS-RECOVERY package will reconcile abandoned `GenerationRun` rows and legacy pending files before changing that behavior. This package does not contact a live provider or server.
