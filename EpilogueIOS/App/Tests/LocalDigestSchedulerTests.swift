import XCTest
@testable import Epilogue
import Domain

final class LocalDigestSchedulerTests: XCTestCase {
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
