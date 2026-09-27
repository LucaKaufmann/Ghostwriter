# SYNC-EDITS-ANDROID: Room 8 upgrade preparation

Base: `ad7fd3e5b05b14c72c4f413e28343b71e1e1fa8d` (server sync PR). This is an isolated test-only probe; Room remains version 8 and no runtime migration is registered.

## Executable evidence

`app/src/test/java/com/example/epilogue/data/local/LegacyRoom8Schema.kt` freezes the three deployed entities in an independent test-only Room 8 database. `Room8UpgradeProbeTest.kt` creates a **real on-disk Room 8** store from that frozen definition, closes it, and reopens it. It pins the deployed Room identity hash `12f91675bc2dd3666434a820d81e3318`, all three SQLite table definitions, the digest-article index, and the cascade foreign key, so a future production version bump cannot silently change the starting fixture. It contains:

- A real feed with `locallyModified=false`, `maxArticles=0`, `lastFetched=1234`, and a legacy server timestamp.
- A real feed with `locallyModified=true`, disabled state, briefing mode, `maxArticles=4`, `lastFetched=9876`, and a legacy server timestamp.
- A persisted `synthetic://wallabag` feed.
- A completed digest, associated article (actual foreign key), and a synthetic EPUB file/path.

The test-only additive SQL transaction adds nullable `serverId`/`serverVersion`, `mutationRevision DEFAULT 0`, a `feed_mutations` outbox with `kind` (including a future delete kind), sent marker, sequence and unique `(serverKey,url,sequence)` index, and `feed_sync_state` rows keyed per server with binding/cursor/diagnostic fields and a persisted `nextSequence`. It backfills **both** real legacy feeds, regardless of the dirty flag, as full four-field `legacy_unresolved` proposals with null server version. Synthetic feeds create no proposal. The provisional `unbound` key and `legacy-*` IDs are probe placeholders and must be replaced or deliberately mapped in the production design before any send; these rows are not sendable automatically.

The probe checks all three original tables and key values, including both dirty flags, fetch timestamps, history relationship and artifact bytes. It proves that removing an outbox row does not reduce the persisted sequence and that another server key has its own counter. It closes and reopens the upgraded SQLite file. A separate injected failure immediately after the feed `ALTER TABLE` statements proves transactional rollback: no new column/table survives, the file remains version 8, and Room 8 reopens its feeds and history. No real app data is read.

Run:

```text
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home \
ANDROID_HOME=/private/tmp/epilogue-backlog-20260927/android-sdk \
ANDROID_SDK_ROOT=/private/tmp/epilogue-backlog-20260927/android-sdk \
./gradlew :app:testDebugUnitTest --tests com.example.epilogue.data.local.Room8UpgradeProbeTest --offline --no-daemon --quiet
```

Result: **3 tests, 0 failures, 0 errors** on 2026-09-27. Existing Robolectric dependency sufficed; no Gradle or lockfile edits.

## Production migration handoff

After the shared KMP ports are accepted, implement actual Room 9 entities and `Migration(8,9)` in the reserved Android files. The Room 8 schema is now frozen independently in `LegacyRoom8Schema.kt`; retain its pinned identity and DDL assertions. Port the additive DDL and backfill pattern, then reopen that Room 8 fixture through the **Room 9 database** so Room validates the complete generated schema and DAO behavior. The current probe deliberately uses raw SQLite after upgrade because production Room 9 does not exist yet; its proposed table columns/index are feasibility evidence, not a frozen generated schema. The final migration must use stable UUIDs for real operation IDs, bind/suspend rows according to the accepted server identity rules, and never send legacy proposals without complete first reconciliation and explicit resolution. Allocate sequence in the same transaction as each edit and retain the per-server counter after outbox deletion.

`SettingsRepository` uses SharedPreferences rather than a Room settings table, so no settings row was present to fixture. The synthetic EPUB is a temporary local file; the database stores only its path. Preserve those stores separately when implementing binding. Do not use destructive fallback for a failed migration. This preparation does not activate v2 sync, replace bulk push, or change any production schema.
