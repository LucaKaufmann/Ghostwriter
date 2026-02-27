# Oracle Review: Background Digest Implementation Plan
*GPT-5.2 via Oracle, 27 February 2026*

---

## Critical Feedback

### 1. Flaws / Gaps / Edge Cases Missing

#### A. "Time-specific background execution" doesn't exist
The plan still implies "7am digest exists because we ran overnight." Reality: many users won't meet overnight constraints (charging + idle + system eligibility). On iOS 17/18 background tasks remain **opportunistic**.

**The actual reliable behavior must be:** digest is ready when the user interacts, and background work is "best effort acceleration."

Must handle:
- User charges midday only
- User never charges overnight (MagSafe on-and-off, car charging, battery packs)
- User kills the app often
- Low Power Mode enabled
- Device under thermal pressure
- Background App Refresh disabled (common!)
- Notification permission denied (common!)

#### B. BGAppRefreshTask "every 1-2 hours" is optimistic
Can be far less frequent or effectively "never" if:
- Background App Refresh disabled
- User rarely opens the app
- System decides app has low priority
- Low Power Mode
- Poor network conditions

**Treat BGAppRefresh as "might run sometimes."**

#### C. Feed refresh handler can easily blow its 30s budget
Looping all feeds and fetching each will:
- Exceed time budget with enough feeds
- Trigger expiration
- **Reduce future scheduling priority** (iOS learns you're expensive)

**Fix:** Design feed refresh as incremental and budget-aware:
- Timebox (10-20s of work)
- Fetch only top N feeds per run
- Prioritize feeds used in next digest window
- Use HTTP caching (ETag / If-Modified-Since) for cheap requests
- Store "last refreshed" / "next due" per feed

#### D. Serious expiration/completion bug in current code
```swift
task.expirationHandler = {
    self.logger.warning(...)
    task.setTaskCompleted(success: false)
}
```
But the work keeps running (no cancellation), and `setTaskCompleted` is also called on success/failure. **Double-complete risk = undefined behavior.**

**Fix:**
- Set expirationHandler before starting work
- Cancel the underlying Task in expiration
- Ensure `setTaskCompleted` called exactly once (use an atomic flag)

#### E. Date logic has subtle bugs
Comparing periods by hour only:
```swift
periods.min(by: { $0.hour < $1.hour })
```
Ignores minutes — wrong if minute-level scheduling is allowed.

Catch-up compares only hour:
```swift
if currentHour >= period.hour { ... }
```
Triggers early (e.g. 07:05 vs period 07:55).

**Fix:** Compare using full (hour, minute) with Calendar date construction.

#### F. Notification scheduling edge cases
- iOS limits pending notifications to **64**. Scheduling per digest ID can hit limits.
- `UNCalendarNotificationTrigger` with only hour/minute (no day) can fire unexpectedly if scheduled after that time passes.
- Need explicit cleanup of pending + delivered notifications.

**Recommendation:** Use one stable daily reminder ID + one stable "ready" ID per day, not per digest UUID.

#### G. App lifecycle scheduling only on willResignActive is insufficient
Users who:
- Keep the app in foreground a lot
- Don't background it cleanly
- App terminated after suspension

**Also schedule on:**
- `didEnterBackground`
- `scenePhase` changes (SwiftUI)
- After successful manual generation
- On settings changes (periods toggled)

---

## Recommended Improvements to the Plan

### 1. Make foreground catch-up the PRIMARY path
Background tasks = acceleration, not delivery mechanism:
```
App opens → is digest stale? → generate in foreground (with loading UI)
            ↓ no
            show cached digest
```

### 2. Budget-aware feed fetching
```swift
func handleFeedRefresh(_ task: BGAppRefreshTask) async {
    let deadline = Date(timeIntervalSinceNow: 20) // Stay under 30s
    let feeds = prioritizedFeeds() // Sort by next-digest relevance
    
    for feed in feeds {
        guard Date() < deadline else { break }
        try? await fetchAndCache(feed)
    }
    
    scheduleFeedRefresh()
    task.setTaskCompleted(success: true)
}
```

### 3. Atomic task completion
```swift
actor TaskCompletionGuard {
    private var completed = false
    
    func complete(_ task: BGTask, success: Bool) {
        guard !completed else { return }
        completed = true
        task.setTaskCompleted(success: success)
    }
}
```

### 4. Consider URLSession background transfers for feed fetching
URLSession background transfers survive app termination and have better system priority than BGAppRefreshTask. Could be used for the RSS XML download step, with processing happening when the download completes.

### 5. iOS 17+: Consider UNNotificationTrigger + App Intents
- `AppIntent` for "Generate Digest" lets users add to Shortcuts/Focus automations
- More reliable than background tasks for users who want precise timing
- Shows up in Spotlight suggestions over time

---

## Summary

The A+C layering is correct directionally, but the plan needs to shift the mental model:

> **Background = best-effort acceleration. Foreground catch-up = guaranteed delivery.**

The plan currently treats background as primary and catch-up as fallback. Flip this: **design for catch-up first, then add background as a bonus.**

---

*Source: GPT-5.2 (ChatGPT browser mode) via Oracle*
