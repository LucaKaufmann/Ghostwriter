import XCTest
@testable import Epilogue
import Domain
import Data
import SwiftData
import BackgroundTasks

final class LocalDigestSchedulerTests: XCTestCase {
    private final class OvernightRequestProbe: @unchecked Sendable {
        private let lock = NSLock()
        private var submittedDates: [Date] = []
        private var pendingDate: Date?
        private var cancellationCount = 0
        private var submittedWithRequiredConditions = true

        func cancel() {
            lock.withLock {
                cancellationCount += 1
                pendingDate = nil
            }
        }

        func submit(_ request: BGProcessingTaskRequest) {
            lock.withLock {
                submittedDates.append(request.earliestBeginDate!)
                pendingDate = request.earliestBeginDate
                submittedWithRequiredConditions = submittedWithRequiredConditions &&
                    request.requiresNetworkConnectivity && request.requiresExternalPower
            }
        }

        var snapshot: (dates: [Date], pending: Date?, cancellations: Int, conditions: Bool) {
            lock.withLock {
                (submittedDates, pendingDate, cancellationCount,
                 submittedWithRequiredConditions)
            }
        }
    }

    private var calendar: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return calendar
    }

    func testLatestElapsedPeriodBeforeFirstScheduleReturnsNil() {
        let now = makeDate(hour: 6, minute: 30)

        let period = LocalDigestScheduler.latestElapsedPeriod(
            now: now,
            periods: [.morning, .noon, .evening],
            calendar: calendar
        )

        XCTAssertNil(period)
    }

    func testLatestElapsedPeriodReturnsMostRecentElapsedPeriod() {
        let now = makeDate(hour: 15, minute: 0)

        let period = LocalDigestScheduler.latestElapsedPeriod(
            now: now,
            periods: [.morning, .noon, .evening],
            calendar: calendar
        )

        XCTAssertEqual(period, .noon)
    }

    func testHasDigestCoveringLatestPeriodMatchesExplicitPeriod() {
        let now = makeDate(hour: 19, minute: 0)
        let digest = makeDigest(
            generatedAt: makeDate(hour: 13, minute: 0),
            period: "EVENING",
            isComplete: true
        )

        let covered = LocalDigestScheduler.hasDigestCoveringLatestPeriod(
            .evening,
            digests: [digest],
            now: now,
            calendar: calendar
        )

        XCTAssertTrue(covered)
    }

    func testHasDigestCoveringLatestPeriodFallsBackToLegacyDigestInLeadWindow() {
        let now = makeDate(hour: 8, minute: 0)
        let legacyDigest = makeDigest(
            generatedAt: makeDate(hour: 5, minute: 30),
            period: nil,
            isComplete: true
        )

        let covered = LocalDigestScheduler.hasDigestCoveringLatestPeriod(
            .morning,
            digests: [legacyDigest],
            now: now,
            calendar: calendar
        )

        XCTAssertTrue(covered)
    }

    func testHasDigestCoveringLatestPeriodIgnoresFailedDigest() {
        let now = makeDate(hour: 19, minute: 0)
        let failedDigest = makeDigest(
            generatedAt: makeDate(hour: 18, minute: 10),
            period: "EVENING",
            isComplete: false,
            errorMessage: "network failure"
        )

        let covered = LocalDigestScheduler.hasDigestCoveringLatestPeriod(
            .evening,
            digests: [failedDigest],
            now: now,
            calendar: calendar
        )

        XCTAssertFalse(covered)
    }

    func testLegacyPendingLocalDigestDoesNotCoverPeriod() {
        let now = makeDate(hour: 8, minute: 0)
        let pending = makeDigest(generatedAt: makeDate(hour: 6, minute: 0),
                                 period: nil, isComplete: false)
        XCTAssertFalse(LocalDigestScheduler.hasDigestCoveringLatestPeriod(
            .morning, digests: [pending], now: now, calendar: calendar))
    }

    @MainActor
    func testReconciledDigestDoesNotCoverPeriodInLoadedMainContext() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("scheduler-recovery-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
        let container = try ModelContainer(
            for: schema, migrationPlan: EpilogueMigrationPlan.self,
            configurations: [ModelConfiguration(
                schema: schema, url: directory.appendingPathComponent("Epilogue.sqlite"))])
        let generatedAt = makeDate(hour: 8, minute: 0)
        let digest = Digest(generatedAt: generatedAt,
                            epubFilePath: directory.appendingPathComponent("missing.epub").path,
                            articleCount: 1, triggerType: .scheduled,
                            isComplete: true, period: "MORNING")
        let run = GenerationRun(attemptSequence: 1, startedAt: generatedAt,
                                trigger: TriggerType.scheduled.rawValue,
                                period: "MORNING", digestId: digest.id)
        let writer = ModelContext(container)
        writer.insert(digest)
        writer.insert(run)
        writer.insert(DigestArticle(
            digest: digest, title: "Article", content: "Body",
            originalUrl: "https://example.test/article",
            feedUrl: "https://feed.test/rss", feedName: "Feed",
            contentType: .deepDive))
        writer.insert(ArticleDelivery(
            feedUrl: "https://feed.test/rss", articleKey: "article-key",
            state: "delivered", firstDigestId: digest.id, committedAt: generatedAt))
        try writer.save()

        let mainContext = ModelContext(container)
        let repository = DigestRepository(modelContext: mainContext)
        let loaded = try XCTUnwrap(mainContext.fetch(FetchDescriptor<Digest>()).first)
        XCTAssertTrue(loaded.isComplete)
        try DeliveryStore(container: container).reconcileInterruptedLocalRuns(
            now: makeDate(hour: 9, minute: 0))
        let now = makeDate(hour: 10, minute: 0)
        let fetched = try await repository.getDigests(from: calendar.startOfDay(for: now),
                                                      to: now)
        XCTAssertEqual(fetched.count, 1)
        XCTAssertFalse(try XCTUnwrap(fetched.first).isComplete)
        XCTAssertFalse(LocalDigestScheduler.hasDigestCoveringLatestPeriod(
            .morning, digests: fetched, now: now, calendar: calendar))
    }

    func testBackgroundCompletionDistinguishesFailureFromNoWork() {
        XCTAssertFalse(LocalDigestScheduler.backgroundTaskSucceeded(.failed))
        XCTAssertFalse(LocalDigestScheduler.backgroundTaskSucceeded(.cancelled))
        XCTAssertFalse(LocalDigestScheduler.backgroundTaskSucceeded(.conflict))
        XCTAssertTrue(LocalDigestScheduler.backgroundTaskSucceeded(nil))
        XCTAssertTrue(LocalDigestScheduler.backgroundTaskSucceeded(.complete))
        XCTAssertTrue(LocalDigestScheduler.backgroundTaskSucceeded(.partial))
        XCTAssertTrue(LocalDigestScheduler.backgroundTaskSucceeded(.empty))
        XCTAssertTrue(LocalDigestScheduler.backgroundTaskSucceeded(.deferred))
    }

    func testHasDigestCoveringLatestPeriodIgnoresMismatchedPeriod() {
        let now = makeDate(hour: 19, minute: 0)
        let digest = makeDigest(
            generatedAt: makeDate(hour: 17, minute: 30),
            period: "NOON",
            isComplete: true
        )

        let covered = LocalDigestScheduler.hasDigestCoveringLatestPeriod(
            .evening,
            digests: [digest],
            now: now,
            calendar: calendar
        )

        XCTAssertFalse(covered)
    }

    @MainActor
    func testProductionCalendarFollowsTimeZoneChangeWhileInjectedCalendarStaysFixed() async throws {
        let originalTimeZone = NSTimeZone.default
        defer { NSTimeZone.default = originalTimeZone }
        let utc = try XCTUnwrap(TimeZone(secondsFromGMT: 0))
        let honolulu = try XCTUnwrap(TimeZone(identifier: "Pacific/Honolulu"))
        NSTimeZone.default = utc

        let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
        let container = try ModelContainer(for: schema, configurations: [
            ModelConfiguration(schema: schema, isStoredInMemoryOnly: true)
        ])
        let context = ModelContext(container)
        let feeds = FeedRepository(modelContext: context)
        let digests = DigestRepository(modelContext: context)
        let settings = SettingsRepository(userDefaults: UserDefaults(
            suiteName: "scheduler-calendar-\(UUID().uuidString)")!)
        try await settings.setEnabledPeriods([.morning])
        try await settings.setGhostwriterEnabled(false)
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-03-01T10:00:00Z"))
        let requestProbe = OvernightRequestProbe()
        let production = LocalDigestScheduler(
            feedRepository: feeds, digestRepository: digests,
            settingsRepository: settings, modelContainer: container,
            now: { now }, cancelOvernightRequest: { requestProbe.cancel() },
            submitOvernightRequest: { requestProbe.submit($0) })
        var fixedUTC = Calendar(identifier: .gregorian)
        fixedUTC.timeZone = utc
        let injected = LocalDigestScheduler(
            feedRepository: feeds, digestRepository: digests,
            settingsRepository: settings, modelContainer: container,
            calendar: fixedUTC)
        let periods: Set<DigestPeriod> = [.morning]
        let utcNext = try XCTUnwrap(injected.nextScheduledDigestTime(from: now, periods: periods))
        XCTAssertEqual(production.nextScheduledDigestTime(from: now, periods: periods), utcNext)
        await production.scheduleOvernightDigest()
        XCTAssertEqual(requestProbe.snapshot.pending,
                       utcNext.addingTimeInterval(-LocalDigestScheduler.scheduledGenerationLeadTime))
        XCTAssertEqual(LocalDigestScheduler.latestElapsedPeriod(
            now: now, periods: periods, calendar: .autoupdatingCurrent), .morning)

        // The same process and scheduler now see March 1 at midnight in Hawaii,
        // rather than March 1 at 10:00 in UTC; morning moves from tomorrow to today.
        NSTimeZone.default = honolulu
        let localNext = try XCTUnwrap(production.nextScheduledDigestTime(from: now, periods: periods))
        XCTAssertEqual(localNext.timeIntervalSince(now),
                       TimeInterval(DigestPeriod.morning.hour * 60 * 60))
        XCTAssertEqual(utcNext.timeIntervalSince(now),
                       TimeInterval((24 - 10 + DigestPeriod.morning.hour) * 60 * 60))
        XCTAssertNotEqual(localNext, utcNext)
        XCTAssertEqual(injected.nextScheduledDigestTime(from: now, periods: periods), utcNext)
        await production.scheduleOvernightDigest() // Foreground resubmission.
        XCTAssertEqual(requestProbe.snapshot.pending,
                       localNext.addingTimeInterval(-LocalDigestScheduler.scheduledGenerationLeadTime))
        XCTAssertEqual(requestProbe.snapshot.dates.count, 2)
        XCTAssertEqual(requestProbe.snapshot.cancellations, 2)
        XCTAssertTrue(requestProbe.snapshot.conditions)
        XCTAssertNil(LocalDigestScheduler.latestElapsedPeriod(
            now: now, periods: periods, calendar: .autoupdatingCurrent))

        try await settings.setGhostwriterEnabled(true)
        await production.scheduleOvernightDigest()
        XCTAssertNil(requestProbe.snapshot.pending)
        XCTAssertEqual(requestProbe.snapshot.dates.count, 2)
        try await settings.setGhostwriterEnabled(false)
        try await settings.setEnabledPeriods([])
        await production.scheduleOvernightDigest()
        XCTAssertNil(requestProbe.snapshot.pending)
        XCTAssertEqual(requestProbe.snapshot.dates.count, 2)
        XCTAssertEqual(requestProbe.snapshot.cancellations, 4)
    }

    private func makeDate(hour: Int, minute: Int) -> Date {
        let components = DateComponents(
            calendar: calendar,
            timeZone: calendar.timeZone,
            year: 2026,
            month: 3,
            day: 1,
            hour: hour,
            minute: minute
        )
        return components.date!
    }

    private func makeDigest(
        generatedAt: Date,
        period: String?,
        isComplete: Bool,
        errorMessage: String? = nil
    ) -> Digest {
        Digest(
            generatedAt: generatedAt,
            epubFilePath: "/tmp/test.epub",
            triggerType: .scheduled,
            isComplete: isComplete,
            errorMessage: errorMessage,
            period: period
        )
    }
}
