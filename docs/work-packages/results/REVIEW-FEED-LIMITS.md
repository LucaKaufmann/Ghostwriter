# REVIEW-FEED-LIMITS

PR82/4115924725: feed max_articles is now explicitly0..2147483647, matching Kotlin Int and the iOS Int32 bridge;0 remains unlimited. Web create/update and legacy request DTOs reject invalid range with422; v2 returns per-item rejected before writing. The contract states the same bound.

Focused web/v2 tests25passed, full backend428passed with three existing warning categories. Fixtures reject negative,Int32overflow andSQLiteoverflow values without changing the feed/version and roundtrip both0 andInt32max through web/v2. Providers/DNS are fixtures. SQLtable shape unchanged, so no migration is required; this validation does not silently rewrite pre-existing off-contract stored data. Native storage/wiretypes already imposeInt32. `git diff --check` passed.

## Legacy stored values — PR106/4116319539

Pre-validation stored caps now project into0..2147483647 on FeedRead, full/incremental v2 snapshots, conflict responses, and replayed historical receipts. Negative legacy values project to0; oversized values project toInt32max. SQLite values, versions, timestamps and receipt JSON remain unchanged by reads. Legacy snapshot no-ops compare the same public representation; new writes remain strictly validated. A later explicit cap edit may replace the old value. This is wire compatibility, not a schema/data migration or change to backend generation's stored configuration.

Seven new API cases cover legacy values through SQLiteInt64max, list/single/v1/v2 reads, conflicts, exact legacy no-op, partial title edits, and both receipt lookup paths (including a concurrent receipt). Focused32passed; full branch backend435passed with three existing warning categories. Ruff on changed model/service/newtest/fixture and diff check passed. The real loopback Kotlin/FastAPI fixture now seeds legacy caps with valid clock versions and asserts decoding through actual Kotlin Int DTOs; live contract1passed, no skips. No production content or providers. Initial fixture test failed because new seed rows shared version0; assigning unique fixture clock versions resolved it without changing production sync behavior.
