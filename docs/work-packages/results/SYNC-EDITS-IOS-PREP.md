# SYNC-EDITS-IOS SwiftData migration feasibility

Date: 2026-09-27. Branch: `codex/sync-edits-ios`, base `ad7fd3e`. This is a test-only probe; no shipping schema, persistence controller, migration plan, lockfile, or generated project source was changed.

## Result

**Proven on the iPhone 16 Pro Max iOS 18.6 simulator:** a disk store created with the current *unversioned* `Domain.Feed`, `Domain.Digest`, and `Domain.DigestArticle` classes can be opened directly by a `SchemaMigrationPlan` whose V1 lists those exact classes and whose V2 adds fields to a captured `Feed` model. A custom `didMigrate` stage copied the four existing feed values into four new proposal fields for every row, including `locallyModified == false`. The migrated V2 container closed and reopened at the same URL; all fixture assertions passed again.

The V1 capture uses `[Domain.Feed, Domain.Digest, Domain.DigestArticle]` through imports, **not** separately declared nested stand-ins. The fixture first constructs `Schema([Feed.self, Digest.self, DigestArticle.self])` and `ModelContainer(for: schema, configurations: [ModelConfiguration(schema: schema, url: url)])`, matching the production controller's unversioned schema/container shape while allowing an explicit temporary disk URL. No V1 container opens or stamps the store between creation and the direct V2 open. `ProbeV2.Feed` repeats the original persisted properties, unique URL, and types, then adds four optional proposal properties. `Digest` and `DigestArticle` remain the actual unchanged Domain model types in both schemas. The plan uses a custom V1→V2 `didMigrate` callback, fetches V2 feeds, populates the proposal fields, and saves.

The fixture contains dirty true and dirty false feeds, plus a synthetic URL. It preserves `url`, `name`, `mode`, `maxArticles` (including 0), `isEnabled`, `lastFetched`, `createdAt`, `serverUpdatedAt`, and `locallyModified` for each; the four proposal fields equal the full current four-field values independent of the dirty flag. It also asserts digest identity, generation time, EPUB path, counts, trigger type, file size, completion/error, remote ID, period, and the article's identity, inverse relationship, content, URLs, content type, order, and word count. The SQLite URL exists after fixture save.

## Reproduction

The executable source is `EpilogueIOS/Modules/Data/Tests/DataTests/SwiftDataMigrationProbeTests.swift`. The probe was run from this worktree with:

```sh
cd EpilogueIOS
tuist install
tuist generate --no-open
cd ..
xcodebuildmcp simulator test \
  --workspace-path /private/tmp/epilogue-backlog-20260927/sync-ios/EpilogueIOS/Epilogue.xcworkspace \
  --scheme Data \
  --simulator-id 3B168BD4-853C-4709-B0BB-DA65DA0B534F \
  --extra-args=-only-testing:DataTests/SwiftDataMigrationProbeTests
```

The `tuist` commands used the existing resolved versions (SwiftSoup 2.13.9, FeedKit 9.1.2, ZIPFoundation 0.9.20). Generation required an ignored build-artifact symlink at `shared/build/XCFrameworks/release/EpilogueShared.xcframework` pointing to the existing output in the sibling `sync-kmp` worktree; no KMP source was copied. The generated workspace and project files are ignored build artifacts. The final focused test run reported **1 passed, 0 failed**. The first attempted project-only run could not resolve the sibling `Domain` module; the generated workspace resolved it. A compile error from using `ModelContainer(for: ProbeV2.self, ...)` was corrected to the supported `ModelContainer(for: schema, migrationPlan: ...)` initializer. The successful run used the corrected source.

## Implementation boundary

This proves the critical existing-store recognition and additive copy path, including the unchanged digest/article relationship. It does **not** prove the complete future V2 feed/outbox/binding model, atomic semantic edits, save-failure rollback, cross-context serialization, a new app-process launch, or the reserved V3 delivery migration. Those remain full SYNC-EDITS-IOS implementation and acceptance tests after the server/KMP contract freezes. The temporary V2 model is a feasibility example, not a proposed complete production schema. Keep the actual V1 captured classes immutable when introducing production versioned schemas; preserving their entity names and persisted property types is essential to this demonstrated path. Do not add reset/delete-store fallback for failed migration.
