# Background Digest Generation — Implementation Plan
*Epilogue iOS — Standalone Mode*
*February 2026 (updated with Oracle review feedback)*

---

## Problem Statement

In standalone mode (Ghostwriter disabled), scheduled digest generation never runs. `BGProcessingTask` is registered and scheduled with `earliestBeginDate` set to specific times (7:00, 12:00, 18:00), but iOS never wakes the app to execute it.

### Root Causes

1. **BGProcessingTask is unreliable for time-specific work.** `earliestBeginDate` is a hint, not a guarantee. iOS can delay execution by hours or days, especially during active device use.
2. **Only one pending task per identifier.** If iOS skips the scheduled run, there's no retry until the next `willResignActive` triggers a reschedule.
3. **No fallback mechanism.** If the background task doesn't fire, the digest is simply never generated.
4. **Duplicate scheduler classes.** Both `LocalDigestScheduler` (App) and `DigestScheduler` (Data module) register for the same task identifier. Only one is wired up — the other is dead code.
5. **@MainActor on heavy work.** `LocalDigestScheduler` is `@MainActor` but digest generation (network I/O, parsing, AI summarization) should run off the main thread.
6. **Double setTaskCompleted bug.** Expiration handler calls `setTaskCompleted(success: false)` but doesn't cancel the running work — the success/failure path also calls it. This is undefined behavior.
7. **Date comparison ignores minutes.** Catch-up logic compares hours only (e.g., 07:05 would trigger for a 07:55 period).

---

## Design Principle

> **Foreground catch-up is the PRIMARY delivery mechanism. Background tasks are best-effort acceleration.**

Many users will never meet background task constraints (Background App Refresh disabled, no overnight charging, Low Power Mode, app killed). The design must guarantee digest delivery when the user opens the app, with background execution as a bonus that makes it instant.

---

## Solution: Multi-Layer Background Strategy (A + C)

Three layers, in order of reliability:

```
Layer 1 (GUARANTEED):  App launch catch-up     → Generate if stale, show loading UI
Layer 2 (LIKELY):      Local notification       → Daily reminder to open the app
Layer 3 (BEST-EFFORT): BGAppRefreshTask         → Pre-fetch feeds (lightweight, ~30s)
Layer 4 (BEST-EFFORT): BGProcessingTask         → Generate digest overnight while charging
```

### Reliability Matrix

| Layer | Reliability | Budget | When | Fails if... |
|-------|------------|--------|------|-------------|
| App launch catch-up | **Guaranteed** | Unlimited (foreground) | User opens app | User never opens app |
| Local notification | **High** | N/A (prompt only) | Scheduled time | Notifications denied |
| BGAppRefreshTask | Medium | ~30 seconds | Every few hours | BAR disabled, Low Power, rarely opened |
| BGProcessingTask | Medium (overnight) | Minutes | Overnight while charging | Not charging, app killed, thermal |

---

## Implementation Details

### Phase 1: Clean Up Existing Code

#### 1.1 Remove Duplicate Scheduler
- **Delete** `Modules/Data/Sources/Data/Services/DigestScheduler.swift` (dead code, same task ID)
- Keep `App/Sources/Services/LocalDigestScheduler.swift` as the single scheduler
- Update any remaining references

#### 1.2 Remove @MainActor from LocalDigestScheduler
- Move to `nonisolated` with explicit `@MainActor` only where needed (UI notifications)
- Digest generation should run on a background thread via `Task.detached(priority: .utility)`

#### 1.3 Fix Double-Complete Bug
Use an atomic guard for all BGTask handlers:

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

All handlers must:
- Set expirationHandler **before** starting work
- **Cancel** the underlying Swift Task in the expiration handler
- Use the guard to ensure `setTaskCompleted` is called exactly once

#### 1.4 Fix Date Comparison Logic
Compare using full (hour, minute) with Calendar date construction, not just hours:

```swift
private func isPassedScheduledTime(for period: DigestPeriod) -> Bool {
    let calendar = Calendar.current
    let now = Date()
    var components = calendar.dateComponents([.year, .month, .day], from: now)
    components.hour = period.hour
    components.minute = period.minute
    guard let scheduledTime = calendar.date(from: components) else { return false }
    return now >= scheduledTime
}
```

#### 1.5 Fix the Stale Print Statement
- Replace `print()` in DigestScheduler.swift:146 with `logger.error()`

---

### Phase 2: App Launch Catch-Up (PRIMARY — Guaranteed)

**This is the most important layer.** When the user opens the app, check if a digest was missed and generate it immediately.

```swift
// In EpilogueApp.swift .task { }
func checkForMissedDigests() async {
    guard let ghostwriterEnabled = try? await settingsRepository.isGhostwriterEnabled(),
          !ghostwriterEnabled else { return }
    
    let enabledPeriods = try? await settingsRepository.getEnabledPeriods()
    guard let periods = enabledPeriods, !periods.isEmpty else { return }
    
    // Check if today's digest exists
    let today = Calendar.current.startOfDay(for: Date())
    let hasDigestToday = try? await digestRepository.hasDigestSince(today)
    
    if hasDigestToday == false {
        // Check if we're past any scheduled period (using full hour:minute comparison)
        let now = Date()
        let calendar = Calendar.current
        
        let hasMissedPeriod = periods.contains { period in
            var components = calendar.dateComponents([.year, .month, .day], from: now)
            components.hour = period.hour
            components.minute = period.minute
            guard let scheduledTime = calendar.date(from: components) else { return false }
            return now >= scheduledTime
        }
        
        if hasMissedPeriod {
            logger.info("Catch-up: generating missed digest for today")
            // Show loading UI, then generate
            await localDigestService.generateDigest()
        }
    }
}
```

**Note:** This needs a loading state in the UI so the user sees progress, not a frozen screen.

---

### Phase 3: Local Notification Reminders (HIGH reliability)

**Purpose:** Prompt the user to open the app at their scheduled digest time. Two modes:

#### 3.1 "Digest Ready" Notification (if overnight generation succeeded)
```swift
private func scheduleMorningNotification(for digest: Digest) async {
    let enabledPeriods = (try? await settingsRepository.getEnabledPeriods()) ?? []
    guard let earliest = enabledPeriods.min(by: {
        ($0.hour, $0.minute) < ($1.hour, $1.minute)
    }) else { return }
    
    // Remove previous ready notification
    UNUserNotificationCenter.current().removePendingNotificationRequests(
        withIdentifiers: ["digest-ready"]
    )
    
    let content = UNMutableNotificationContent()
    content.title = "📖 Your Digest is Ready"
    content.body = "\(digest.articleCount) articles from your feeds"
    content.sound = .default
    content.categoryIdentifier = "DIGEST_READY"
    
    var dateComponents = DateComponents()
    dateComponents.hour = earliest.hour
    dateComponents.minute = earliest.minute
    
    let trigger = UNCalendarNotificationTrigger(dateMatching: dateComponents, repeats: false)
    let request = UNNotificationRequest(
        identifier: "digest-ready",  // Stable ID, not per-digest
        content: content,
        trigger: trigger
    )
    
    try? await UNUserNotificationCenter.current().add(request)
}
```

#### 3.2 Standing Daily Reminder (fallback if overnight didn't run)
```swift
func scheduleDigestReminderNotification() async {
    let enabledPeriods = (try? await settingsRepository.getEnabledPeriods()) ?? []
    guard let earliest = enabledPeriods.min(by: {
        ($0.hour, $0.minute) < ($1.hour, $1.minute)
    }) else { return }
    
    let content = UNMutableNotificationContent()
    content.title = "📖 Time for Your Digest"
    content.body = "Tap to generate your morning reading digest"
    content.sound = .default
    content.categoryIdentifier = "DIGEST_REMINDER"
    
    var dateComponents = DateComponents()
    dateComponents.hour = earliest.hour
    dateComponents.minute = earliest.minute
    
    // Repeating daily — replaced by "ready" when overnight succeeds
    let trigger = UNCalendarNotificationTrigger(dateMatching: dateComponents, repeats: true)
    let request = UNNotificationRequest(
        identifier: "daily-digest-reminder",  // Stable ID
        content: content,
        trigger: trigger
    )
    
    try? await UNUserNotificationCenter.current().add(request)
}
```

**Notification ID Strategy:** Only 2 stable IDs (`digest-ready`, `daily-digest-reminder`). Never use per-digest UUIDs — iOS limits pending notifications to 64.

#### 3.3 Notification Actions
```swift
let readAction = UNNotificationAction(
    identifier: "READ_DIGEST",
    title: "Read Now",
    options: [.foreground]
)

let generateAction = UNNotificationAction(
    identifier: "GENERATE_DIGEST", 
    title: "Generate Now",
    options: [.foreground]
)

let readyCategory = UNNotificationCategory(
    identifier: "DIGEST_READY",
    actions: [readAction],
    intentIdentifiers: []
)

let reminderCategory = UNNotificationCategory(
    identifier: "DIGEST_REMINDER",
    actions: [generateAction],
    intentIdentifiers: []
)

UNUserNotificationCenter.current().setNotificationCategories([readyCategory, reminderCategory])
```

---

### Phase 4: BGAppRefreshTask for Feed Pre-Fetching (BEST-EFFORT)

**Purpose:** Keep RSS feed content fresh so digest generation is fast when triggered (foreground or background).

#### 4.1 New Task Identifier
```
com.epilogue.app.feedRefresh
```
Add to `BGTaskSchedulerPermittedIdentifiers` in Project.swift.

#### 4.2 Budget-Aware Handler
The 30-second budget is tight. Design for incremental, timeboxed fetching:

```swift
func handleFeedRefresh(_ task: BGAppRefreshTask) async {
    let guard = TaskCompletionGuard()
    
    // Schedule next refresh immediately
    scheduleFeedRefresh()
    
    let fetchTask = Task {
        let deadline = Date(timeIntervalSinceNow: 20) // Stay well under 30s
        let feeds = try await feedRepository.getAllFeeds()
            .sorted { ($0.lastFetchedAt ?? .distantPast) < ($1.lastFetchedAt ?? .distantPast) }
        
        var fetchedCount = 0
        for feed in feeds {
            guard Date() < deadline else {
                logger.info("Feed refresh timeboxed after \(fetchedCount) feeds")
                break
            }
            try Task.checkCancellation()
            try await feedParser.fetchAndCache(feed, 
                useETag: true,           // Skip unchanged feeds
                useIfModifiedSince: true  // HTTP 304 = cheap
            )
            fetchedCount += 1
        }
        
        await guard.complete(task, success: true)
    }
    
    task.expirationHandler = {
        fetchTask.cancel()
        Task { await guard.complete(task, success: false) }
    }
}
```

**Key constraints:**
- Timebox to 20s (leave margin for the 30s budget)
- Sort feeds by "least recently fetched" — round-robin across runs
- Use HTTP caching headers (ETag / If-Modified-Since) so unchanged feeds are near-zero cost
- iOS learns you're cheap = higher scheduling priority

#### 4.3 Scheduling
```swift
func scheduleFeedRefresh() {
    let request = BGAppRefreshTaskRequest(identifier: "com.epilogue.app.feedRefresh")
    request.earliestBeginDate = Date(timeIntervalSinceNow: 60 * 60) // 1 hour
    try? BGTaskScheduler.shared.submit(request)
}
```

---

### Phase 5: BGProcessingTask for Overnight Digest Generation (BEST-EFFORT)

**Purpose:** Generate the full digest (with AI summaries + EPUB) overnight while charging. This is a bonus — if it works, the user gets an instant "Digest Ready" notification. If it doesn't, catch-up handles it.

#### 5.1 Overnight Scheduling
```swift
func scheduleOvernightDigest() async {
    BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: Self.taskIdentifier)
    
    guard let ghostwriterEnabled = try? await settingsRepository.isGhostwriterEnabled(),
          !ghostwriterEnabled else { return }
    
    let enabledPeriods = (try? await settingsRepository.getEnabledPeriods()) ?? []
    guard !enabledPeriods.isEmpty else { return }
    
    // Find earliest period for tomorrow
    let earliestPeriod = enabledPeriods.min(by: {
        ($0.hour, $0.minute) < ($1.hour, $1.minute)
    })!
    
    let calendar = Calendar.current
    let tomorrow = calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: Date()))!
    var components = calendar.dateComponents([.year, .month, .day], from: tomorrow)
    components.hour = earliestPeriod.hour
    components.minute = earliestPeriod.minute
    let nextDigestTime = calendar.date(from: components)!
    
    let request = BGProcessingTaskRequest(identifier: Self.taskIdentifier)
    // 2 hours before earliest period to give iOS time
    request.earliestBeginDate = nextDigestTime.addingTimeInterval(-2 * 3600)
    request.requiresNetworkConnectivity = true
    request.requiresExternalPower = true  // Overnight while charging
    
    try? BGTaskScheduler.shared.submit(request)
    logger.info("Scheduled overnight digest generation before \(nextDigestTime)")
}
```

#### 5.2 Handler with Proper Cancellation
```swift
private func handleBackgroundTask(_ task: BGProcessingTask) async {
    logger.info("Overnight digest task started")
    let completionGuard = TaskCompletionGuard()
    
    // Schedule next overnight run immediately
    await scheduleOvernightDigest()
    
    let generationTask = Task.detached(priority: .utility) { [self] in
        let generator = try await self.buildDigestGenerator()
        return try await generator.generateDigest(triggerType: .scheduled)
    }
    
    task.expirationHandler = {
        generationTask.cancel()
        self.logger.warning("Overnight digest task expired")
        Task { await completionGuard.complete(task, success: false) }
    }
    
    do {
        let digest = try await generationTask.value
        logger.info("Overnight digest complete: \(digest.articleCount) articles")
        
        // Schedule "ready" notification for morning
        await scheduleMorningNotification(for: digest)
        
        await completionGuard.complete(task, success: true)
    } catch {
        logger.error("Overnight digest failed: \(error)")
        await completionGuard.complete(task, success: false)
    }
}
```

---

## Updated Info.plist Task Identifiers

```xml
<key>BGTaskSchedulerPermittedIdentifiers</key>
<array>
    <string>com.epilogue.app.digestgeneration</string>
    <string>com.epilogue.app.feedRefresh</string>
    <string>com.epilogue.app.feedSync</string>
    <string>com.epilogue.app.digestSync</string>
</array>
```

---

## Updated App Lifecycle

Schedule background tasks from **multiple touchpoints**, not just `willResignActive`:

```swift
// EpilogueApp.swift

var body: some Scene {
    WindowGroup {
        ContentView()
            .task {
                // Initial sync
                await ghostwriterCoordinator.performFullSync()
                
                // PRIMARY: Catch-up — generate missed digest if needed
                await checkForMissedDigests()
                
                // Set up standing daily reminder notification
                await localDigestScheduler?.scheduleDigestReminderNotification()
                
                // Register notification categories
                registerNotificationCategories()
            }
            .onChange(of: scenePhase) { _, newPhase in
                if newPhase == .background {
                    scheduleAllBackgroundWork()
                }
            }
            .onReceive(NotificationCenter.default.publisher(
                for: UIApplication.willResignActiveNotification
            )) { _ in
                scheduleAllBackgroundWork()
            }
    }
}

private func scheduleAllBackgroundWork() {
    backgroundTaskManager?.scheduleBackgroundTasks()
    Task {
        await localDigestScheduler?.scheduleFeedRefresh()
        await localDigestScheduler?.scheduleOvernightDigest()
    }
}
```

Also reschedule after:
- Manual digest generation completes
- Settings changes (periods toggled on/off)
- Ghostwriter mode toggled

---

## Execution Flow (Happy Path — overnight works)

```
6:00 PM  User closes app
         → scheduleFeedRefresh() (1h from now)
         → scheduleOvernightDigest() (before 7:00 AM, requires charging)

7:00 PM  BGAppRefreshTask fires → top N feeds cached (within 20s budget)
         → reschedules for 8:00 PM

11:00 PM Device plugged in, idle
         → BGProcessingTask fires
         → Generates digest from cached feeds + AI summaries
         → Saves digest locally
         → Schedules "📖 Your Digest is Ready" notification for 7:00 AM

7:00 AM  Notification appears → user taps → app opens → digest is waiting
```

## Execution Flow (Fallback — overnight didn't run)

```
6:00 PM  User closes app → all background tasks scheduled

Overnight: BGProcessingTask never fires (device not charged)

7:00 AM  "📖 Time for Your Digest" daily reminder notification
         → User taps → app opens
         → checkForMissedDigests() detects no digest today
         → Shows loading UI → generates digest in foreground
         → Digest ready in ~30-60 seconds
```

## Execution Flow (Worst case — no notifications)

```
User has notifications denied, BAR disabled, never charges overnight

Sometime later: User opens app
         → checkForMissedDigests() detects no digest today
         → Generates in foreground
         → Always works, just not instant
```

---

## Testing

### Simulate BGProcessingTask (Xcode debugger)
```
e -l objc -- (void)[[BGTaskScheduler sharedScheduler] _simulateLaunchForTaskWithIdentifier:@"com.epilogue.app.digestgeneration"]
```

### Simulate BGAppRefreshTask
```
e -l objc -- (void)[[BGTaskScheduler sharedScheduler] _simulateLaunchForTaskWithIdentifier:@"com.epilogue.app.feedRefresh"]
```

### Verify Scheduled Tasks
```
e -l objc -- (void)[[BGTaskScheduler sharedScheduler] _simulateExpirationForTaskWithIdentifier:@"com.epilogue.app.digestgeneration"]
```

---

## Task Breakdown

- [ ] **Phase 1:** Clean up
  - [ ] Delete duplicate `DigestScheduler.swift`
  - [ ] Remove `@MainActor` from `LocalDigestScheduler`
  - [ ] Add `TaskCompletionGuard` actor
  - [ ] Fix double-complete bug in all handlers
  - [ ] Fix date comparison to use full hour:minute
  - [ ] Replace stale `print()` with `logger.error()`
- [ ] **Phase 2:** App launch catch-up (foreground, guaranteed)
  - [ ] Implement `checkForMissedDigests()`
  - [ ] Add `hasDigestSince()` to `DigestRepository`
  - [ ] Add loading UI state for catch-up generation
- [ ] **Phase 3:** Local notification system
  - [ ] Standing daily reminder (repeating, stable ID)
  - [ ] "Digest Ready" notification (after overnight success, stable ID)
  - [ ] Register notification categories + actions
  - [ ] Clean up delivered notifications on app open
- [ ] **Phase 4:** BGAppRefreshTask for feed pre-fetching
  - [ ] Add `com.epilogue.app.feedRefresh` to permitted identifiers
  - [ ] Budget-aware handler (20s timebox, round-robin feeds, ETag caching)
  - [ ] Store `lastFetchedAt` per feed
- [ ] **Phase 5:** BGProcessingTask overnight
  - [ ] `requiresExternalPower = true`
  - [ ] Proper cancellation in expiration handler
  - [ ] Schedule "ready" notification on success
- [ ] **Lifecycle:** Schedule from multiple touchpoints
  - [ ] `onChange(of: scenePhase)`
  - [ ] `willResignActive`
  - [ ] After manual generation
  - [ ] After settings changes
- [ ] **Testing:** Verify with Xcode simulator commands

---

## Future Considerations

- **iOS 18 App Intents:** Register a "Generate Digest" AppIntent for Shortcuts/Focus automations
- **WidgetKit Timeline:** Widget refresh can piggyback digest generation
- **URLSession background transfers:** For feed downloads that survive app termination (more reliable than BGAppRefreshTask for the download step)
- **Push Notifications (optional):** Even in standalone mode, a lightweight push service could wake the app — but adds server dependency

---

*Reviewed by Oracle (GPT-5.2). See `docs/oracle-review-background-plan.md` for full review.*
