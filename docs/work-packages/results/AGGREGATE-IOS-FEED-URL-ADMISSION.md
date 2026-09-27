# Aggregate iOS feed URL admission

iOS source: `470e83496d1478e577c235e4ff30c74662137911` on `codex/aggregate-ios-feed-url-admission`, based on `0987f80d4b16973cb00212545d5de6bb849e4369`. Shared helper dependency: `c63ded14186afa4e0e28ef5f694b931576a66654` on the separate aggregate admission branch.

New feed edits now call the common `FeedSyncV2ModelsKt.isAdmissibleNewFeedUrlV2(url:)` predicate after looking up an exact persisted feed row. The existing broad URL check remains in place. A known row skips only the new admission predicate, preserving legacy URL edits and queued wire identity. The predicate never replaces or normalizes the stored URL. Invalid new URLs use the existing `invalidURL` error path before feed, mutation, or state insertion.

The existing Add Feed view catches that error, displays its localized message, and dismisses the form only after a successful edit; no UI code was changed.

The disk-backed SwiftData tests prove rejection of `http://:8080/rss` and ports 0 and 99999 without persisted records, acceptance of an IPv6 URL with exact raw spelling in the serialized KMP claim, and editing a previously persisted hostless legacy URL without changing its key or base version.

Evidence on iPhone 16 Plus, iOS 18.6:

- The pre-fix simulator regression failed because all three invalid URLs were accepted and persisted: `/private/tmp/epilogue-backlog-20260927/aggregate-ios-feed-url-admission-red.log`.
- The single shared XCFramework build from `c63ded1` passed in 3m 9s; its generated simulator header exports `isAdmissibleNewFeedUrlV2(url:)`: `/private/tmp/epilogue-backlog-20260927/aggregate-feed-url-admission-native-build.log`.
- Shared `iosSimulatorArm64Test` passed 59/59 from that commit: `/private/tmp/epilogue-backlog-20260927/aggregate-feed-url-admission-native-test.log` and its XML results.
- Focused `FeedV2StoreTests` passed 55/55: `/private/tmp/epilogue-backlog-20260927/aggregate-ios-feed-url-admission-focused.log`.
- Full `Epilogue-Workspace` unit tests, excluding UI, passed 197/197: `/private/tmp/epilogue-backlog-20260927/aggregate-ios-feed-url-admission-workspace-test.log`.
- Explicit Epilogue App simulator build passed: `/private/tmp/epilogue-backlog-20260927/aggregate-ios-feed-url-admission-app-build.log`.

The iOS test worktree used an ignored symlink to the XCFramework built from `c63ded1` while its own Git branch intentionally contains no shared-source changes. The isolated review flagged that missing Git dependency rather than an iOS call-site defect. The integrated-source Sol review with the helper present found no actionable findings (`/private/tmp/epilogue-backlog-20260927/ios-feed-url-admission-integrated-review.json`). No production transport or provider was used.
