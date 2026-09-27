# AGGREGATE-FEED-URL-ADMISSION

Acceptance base: published `0987f80` on `codex/aggregate-feed-url-admission`. Finding: PR119 `4116909638`.

New local feed admission now uses exported common `isAdmissibleNewFeedUrlV2`, backed by the existing tested HTTP URL parser only as a Boolean check. Neither the helper nor Android callers replace the user's raw URL key. Android Add rejects malformed URLs before closing its dialog, and the Room store repeats the check when no feed row exists. Existing rows still use the original v2 shape check, so edits to known legacy URLs remain possible.

The original `isFeedUrlV2` remains on wire serialization and server snapshot validation. This preserves previously queued payload replay and reading historical snapshots even if their URL would fail new admission. Local validation checks syntax, host, and port; backend DNS and public-host policy remain authoritative for new creation.

Focused tests cover hostless and malformed ports, valid bracketed IPv6 and raw path/query identity, Android Add state, Room first insert, known legacy edit, and legacy snapshot/wire replay. `:shared:testDebugUnitTest --tests '*FeedSyncV2TransportTest'` passed 6/6. `:app:testDebugUnitTest --tests '*AndroidFeedV2StoreTest' --tests '*FeedViewModelTest'` passed 35/35. Both used `--offline --no-daemon`, with zero failures/errors. Logs: `/private/tmp/epilogue-backlog-20260927/feed-url-shared-focused.log` and `/private/tmp/epilogue-backlog-20260927/feed-url-android-focused.log`. Full Android/shared/debug build remains for acceptance after independent source review.
