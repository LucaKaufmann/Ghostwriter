# Rejected feed URL with queued edits

The `invalid_url` resolution guidance now tells the user to resolve any remaining proposals for the old URL after discarding the rejected proposal. It names Keep removed only for a feed absent from the server, then directs the user to add the corrected URL. Feed mutation storage, ordering, and server communication are unchanged.

The debug-only SwiftData fixture includes a rejected null-base create followed by a pending edit for the same URL. Its UI test demonstrates Discard → remaining attention row → Keep removed → old row gone → Add with a corrected URL. The prior single-proposal, title-correction, and rejected-delete checks remain.

## Verification

- Source commits: `67ae3d86166c786ec8fe477f270a84ab5c576420` and `c2f072d97f06308f7713e23866d0ebc89c961bb6`, based on main `174a349cb145342ce129249762b458334851eae8`.
- Focused first run: two interaction tests passed; screenshot fixture hit XCTest's 128-character exact-query limit. Log: `/private/tmp/epilogue-backlog-20260927/review-ios-invalid-url-successor-ui.log`.
- Guidance now has a stable accessibility identifier. The screenshot fixture rerun passed **1/1**. Log: `/private/tmp/epilogue-backlog-20260927/review-ios-invalid-url-successor-ui-fixture-rerun.log`.
- Saved-result fixture and successor UI tests passed **2/2**. Result bundle: `/private/tmp/epilogue-backlog-20260927/review-ios-invalid-url-successor-evidence.xcresult`; log: `/private/tmp/epilogue-backlog-20260927/review-ios-invalid-url-successor-evidence.log`.
- `xcodebuildmcp simulator build` for `Epilogue-Workspace` passed. Log: `/private/tmp/epilogue-backlog-20260927/review-ios-invalid-url-successor-app-build.log`.
- Inspected screenshots: [updated rejected guidance](assets/ios-invalid-url-successor/rejected-guidance.png) and [remaining proposal with Keep removed](assets/ios-invalid-url-successor/remaining-proposal.png). The text and actions are readable without clipping.

These tests use synthetic in-memory feed state and do not make server or provider requests. The three-case focused suite will run on the merged main commit; the existing 197-unit suite already passed on its parent main revision, with no store or model changes here.
