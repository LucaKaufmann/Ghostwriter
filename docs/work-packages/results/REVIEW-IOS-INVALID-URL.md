# Rejected feed URL resolution

The feed resolution sheet now treats a server `invalid_url` rejection of an upsert as a URL decision. It explains that the proposal cannot change its URL and offers Discard so the user can add the feed with a corrected URL. Other rejected upserts retain title correction; rejected deletes retain their discard flow.

The debug-only UI fixture uses an isolated UserDefaults suite with the server URL matching its in-memory SwiftData binding. This makes the discard-to-add interaction testable without touching the app's normal configured URL.

## Verification

- Source: `8279046a2c64c980865f710c11e868a711a73365` plus fixture correction `548a817b1db41cd27c8588c8a686624a1215e24b`.
- `xcodebuildmcp simulator test`, `Epilogue-Workspace`, iPhone 16 Plus (iOS 18.6), selected `testFeedResolutionFixture` and `testInvalidURLProposalDiscardsBeforeCorrectedAdd`: **2 passed, 0 failed**. Log: `/private/tmp/epilogue-backlog-20260927/review-ios-invalid-url-ui-final.log`.
- A saved-result rerun of `testFeedResolutionFixture`: **1 passed, 0 failed**. Result bundle: `/private/tmp/epilogue-backlog-20260927/review-ios-invalid-url-ui-evidence.xcresult`. Log: `/private/tmp/epilogue-backlog-20260927/review-ios-invalid-url-evidence.log`.
- `xcodebuildmcp simulator build`, `Epilogue-Workspace`, same simulator: **passed**. Log: `/private/tmp/epilogue-backlog-20260927/review-ios-invalid-url-app-build.log`.
- The rendered [invalid URL resolution sheet](assets/ios-invalid-url/rejected-invalid-url.png) was inspected. It shows the guidance and Discard action without title correction or clipping.

The UI tests use synthetic fixture rows and do not make a server or provider request. The main-branch full workspace gate is reserved for the merged commit.
