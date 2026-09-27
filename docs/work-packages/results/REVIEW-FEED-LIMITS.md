# REVIEW-FEED-LIMITS

PR82/4115924725: feed max_articles is now explicitly0..2147483647, matching Kotlin Int and the iOS Int32 bridge;0 remains unlimited. Web create/update and legacy request DTOs reject invalid range with422; v2 returns per-item rejected before writing. The contract states the same bound.

Focused web/v2 tests25passed, full backend428passed with three existing warning categories. Fixtures reject negative,Int32overflow andSQLiteoverflow values without changing the feed/version and roundtrip both0 andInt32max through web/v2. Providers/DNS are fixtures. SQLtable shape unchanged, so no migration is required; this validation does not silently rewrite pre-existing off-contract stored data. Native storage/wiretypes already imposeInt32. `git diff --check` passed.
