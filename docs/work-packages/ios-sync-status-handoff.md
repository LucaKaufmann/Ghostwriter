# iOS sync outcome handoff

Prepared 2026-09-27 from current sync-ios coordinator and accepted shared base99fcda5. This is implementation planning, not acceptance. Root must supply the final accepted iOS sync base before coordinator ownership transfers.

## Prerequisites and ownership

Digest ingestion commit574b23be681a4dfec5cff64c7c9c1233187ee737 on `codex/ios-digest-sync-outcomes` keeps the public async-throws API, preserves successful siblings and throws `DigestSyncIngestionError` for incomplete required ingestion. Six actual SwiftData service fixtures and independent Sol review passed. Historical already-incomplete rows are not repaired. Root integrates this commit onto the accepted iOS sync base.

The separate config-sync-outcomes owner is correcting proven false success in shared `ConfigSyncUseCase` and iOS `ConfigSyncManager`. Public Boolean signatures remain stable; failed pushes preserve retry state and cannot return success. This is still in implementation. Coordinator must consume false/throws explicitly.

Coordinator work owns `GhostwriterSyncCoordinator`, its dedicated tests, and narrow status presentation as necessary after the feed owner releases them. No v1 feed writes/apply paths may return. Feed outbox/schema and generation/delivery belong to their respective owners.

## Intended behavior

Normal and forced entry points share one outcome policy. Use a single run implementation with a force-digests parameter, retain published status/public methods, clear the running flag with defer, and advance last overall success only after every required component succeeds. A settings read error is a failure; an actually unconfigured app is a skipped run. Heartbeat is optional.

Keep feed v2 independent so its failure does not prevent config/digest/schedule work. A fetched combined response is applied component by component; config, digest or schedule apply failures remain visible and preserve successful siblings. Do not reinterpret apply failure as endpoint unavailability or dispatch fallback after it.

Only combined fetch/transport failure enters individual fallback. Distinguish typed404/405 unsupported endpoint from transient transport errors. Fallback may recover a fetch failure if all required work succeeds; it must include schedule fetch/apply, config and eligible digest work. Normal digest cadence can skip digest ingestion; forced sync cannot. Cancellation stops later operations and fallback, preserves the prior success timestamp and releases the running flag. Check Swift task cancellation around exported Kotlin suspend calls; do not claim immediate transport cancellation without evidence.

The combined schedules payload predates a possible local-newer config upload. After successful config reconciliation, fetch current schedules before applying their times; accept this extra read request to avoid overwriting newly synchronized settings. If config fails with pending local fields, preserve those times; independently applying enabled states must not hide the config failure. Cover stale-combined schedule timing in tests. Keep the shared Boolean API unchanged.

Use a typed aggregate of component/phase failures for the existing status surface. Preserve the feed-upgrade preview action when a feed error is nested in an aggregate. Preserve pending feed writes and successful digest siblings. No raw source content, credentials or provider calls in fixtures or diagnostics.

## Required checks

Test both public entry points using injected service closures and fixed time, with real temporary SwiftData/settings and actual digest-service fixtures where persistence matters:

- Complete combined run advances success once; no errors.
- Config apply, schedule save and mixed/all digest ingestion failures each preserve successful siblings, report the failed component, keep prior overall success and never invoke fallback.
- Feed v2 partial/failure/upgrade/server-change leaves pending writes intact while other components run; no v1 feed path.
- Typed404/405 enters individual fallback; transient fetch failure may recover without being mislabeled unsupported.
- Every fallback component failure remains visible, successful siblings persist, and no success time advances.
- Normal cadence skips digest; forced mode invokes it and reports its failure.
- Cancellation during feed/fetch/apply/fallback stops subsequent work, clears isSyncing, preserves success time and does not dispatch fallback.
- Unconfigured versus configuration-read failure have distinct outcomes.
- Retry the same partial digest payload successfully without duplicate remote IDs; retain explicit limits for historically incomplete rows.

Regenerate Tuist from source and use the final native feed owner's corrected single-runtime linking arrangement. Run affected shared and App checks plus simulator build, inspect the status surface, and independently review the resulting combined change. Merges/releases/deployment remain outside scope.
