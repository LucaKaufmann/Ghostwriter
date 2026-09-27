# DELIVERY-IDENTITY result

Implemented the shared article-link identity prerequisite from `docs/contracts/feed-sync-and-local-delivery.md` section 2. `ArticleDeliveryIdentity.fromArticleLink(String?)` returns `ArticleIdentityResult.Valid(normalizedUrl, articleKey)` or `Invalid`; invalid links cannot produce an empty or fallback hash. The helper is callable from Android and the generated iOS framework. It does not normalize the exact stored feed URL key.

Normalization accepts absolute HTTP(S) links only. It lowercases the scheme and host, removes default ports and fragments, supplies `/` for an empty path, brackets IPv6, and preserves the raw path case, query order and duplicates, percent-escape case, and nondefault port text. It rejects user-info, malformed hosts/ports/percent escapes, invalid ASCII URI characters, whitespace/control characters, and unpaired UTF-16 surrogates. Valid non-ASCII path/query characters remain unchanged and are hashed as UTF-8. The SHA-256 implementation is Java `MessageDigest` on Android and Apple CommonCrypto on iOS; no crypto dependency or custom hash implementation was added.

Common golden fixtures assert literal normalized strings and literal SHA-256 digests calculated independently with Python `hashlib`. They cover default and nondefault ports including zero-padded default ports, empty path and query, query duplicates/order, percent-escape case, path case, bracketed and IPv4-embedded IPv6, Unicode, user-info, malformed IP/host/port, bad percent escapes, and unpaired surrogates.

Verification on the isolated `codex/delivery-identity-core` worktree (base `ad7fd3e5b05b14c72c4f413e28343b71e1e1fa8d`):

- `:shared:testDebugUnitTest --offline --no-daemon`: 21 tests, 0 failures.
- `:shared:iosSimulatorArm64Test --offline --no-daemon`: 21 tests, 0 failures; actual CommonCrypto code and common vectors ran on the iOS simulator.
- `git diff --check`: clean.

The current base's older `GhostwriterApiClientTest.kt` uses two `String.toByteArray()` calls that cannot compile for Kotlin/Native. For the iOS test only, these two calls were temporarily changed to `encodeToByteArray()` and then restored before commit. The separate KMP lane owns the permanent two-line portability fix, so this branch's unchanged base alone cannot rerun the iOS common tests until that fix is integrated. No Android or iOS generation caller has cut over to this helper yet; no native fallback parity or deliver-once behavior is claimed here. No schema, UI, generation flow, or provider call changed.
