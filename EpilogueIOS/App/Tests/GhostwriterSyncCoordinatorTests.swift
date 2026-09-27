import Foundation
import SwiftData
import XCTest
import Domain
import Data
import GhostwriterClient
@testable import Epilogue

@MainActor
final class GhostwriterSyncCoordinatorTests: XCTestCase {
    private enum FixtureError: Error { case feed, config, digest, schedule, read, download }
    private let fixedNow = Date(timeIntervalSince1970: 1_800_000_000)

    @MainActor private struct Fixture {
        let container: ModelContainer
        let settings: SettingsRepository
        let digests: DigestRepository
        let coordinator: GhostwriterSyncCoordinator

        init(now: Date) async throws {
            let directory = FileManager.default.temporaryDirectory
                .appendingPathComponent("sync-status-\(UUID().uuidString)", isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
            let configuration = ModelConfiguration(schema: schema,
                url: directory.appendingPathComponent("Epilogue.sqlite"))
            container = try ModelContainer(for: schema, migrationPlan: EpilogueMigrationPlan.self,
                                           configurations: [configuration])
            let defaults = UserDefaults(suiteName: "sync-status-\(UUID().uuidString)")!
            settings = SettingsRepository(userDefaults: defaults, modelContainer: container)
            try await settings.setGhostwriterEnabled(true)
            try await settings.setGhostwriterURL("https://example.invalid")
            let context = ModelContext(container)
            digests = DigestRepository(modelContext: context)
            let feeds = FeedRepository(modelContext: context)
            coordinator = GhostwriterSyncCoordinator(settingsRepository: settings,
                feedRepository: feeds, digestRepository: digests, modelContainer: container)
            coordinator.now = { now }
            coordinator.operations.heartbeat = {}
            coordinator.operations.feed = { _ in }
            coordinator.operations.fetchCombined = { _, _ in try Self.response() }
            coordinator.operations.fetchSchedules = { Self.schedule(hour: 8) }
            coordinator.operations.applyConfig = { _ in }
            coordinator.operations.syncConfig = { true }
            coordinator.operations.knownDigestIDs = { [] }
            coordinator.operations.applyDigests = { _, _ in }
            coordinator.operations.syncDigests = { _ in }
        }

        static func schedule(hour: Int, enabled: Bool = true) -> [ScheduleResponse] {
            let json = """
            [{"id":"morning","period":"morning","hour":\(hour),"minute":0,
              "enabled":\(enabled),"timezone":"UTC"}]
            """
            return try! JSONDecoder().decode([ScheduleResponse].self, from: Data(json.utf8))
        }

        static func response(digests: String = "[]",
                             serverTimestamp: String = "2026-09-27T10:00:00Z") throws -> SyncResponse {
            let json = """
            {"config":{"timezone":"UTC","updated_at":"2026-09-27T10:00:00Z"},
             "feeds":{"feeds":[],"tombstones":[],"server_timestamp":"\(serverTimestamp)"},
             "digests":{"new_digests":\(digests)},
             "schedules":[{"id":"morning","period":"morning","hour":6,"minute":0,
                           "enabled":true,"timezone":"UTC"}]}
            """
            return try JSONDecoder().decode(SyncResponse.self, from: Data(json.utf8))
        }
    }

    private func run(_ coordinator: GhostwriterSyncCoordinator, force: Bool) async {
        if force { await coordinator.performFullSyncIncludingDigests() }
        else { await coordinator.performFullSync() }
    }

    private func issues(_ coordinator: GhostwriterSyncCoordinator) -> [SyncIssue] {
        (coordinator.lastSyncError as? SyncRunError)?.issues ?? []
    }

    func testBothEntriesCompleteCombinedRunAndRefreshStaleSchedule() async throws {
        for force in [false, true] {
            let fixture = try await Fixture(now: fixedNow)
            try await fixture.settings.setGhostwriterSchedule(
                morningHour: 7, morningMinute: 0, noonHour: 12, noonMinute: 0,
                eveningHour: 18, eveningMinute: 0, timezone: "UTC")
            var events: [String] = []
            fixture.coordinator.operations.feed = { _ in events.append("feed") }
            fixture.coordinator.operations.applyConfig = { _ in events.append("config") }
            fixture.coordinator.operations.applyDigests = { _, _ in events.append("digest") }
            fixture.coordinator.operations.fetchSchedules = {
                events.append("fresh schedules")
                return Fixture.schedule(hour: 8)
            }
            fixture.coordinator.operations.syncConfig = { XCTFail("No fallback"); return false }
            await run(fixture.coordinator, force: force)
            XCTAssertEqual(fixture.coordinator.lastSyncTime, fixedNow)
            XCTAssertNil(fixture.coordinator.lastSyncError)
            XCTAssertFalse(fixture.coordinator.isSyncing)
            let schedule = try await fixture.settings.getGhostwriterSchedule()
            XCTAssertEqual(schedule?.morningHour, 8)
            XCTAssertEqual(events, ["feed", "config", "digest", "fresh schedules"])
        }
    }

    func testConfigFailurePreservesLocalTimesWhileDigestAndEnabledStateSucceed() async throws {
        for force in [false, true] {
            let fixture = try await Fixture(now: fixedNow)
            try await fixture.settings.setGhostwriterSchedule(
                morningHour: 7, morningMinute: 0, noonHour: 12, noonMinute: 0,
                eveningHour: 18, eveningMinute: 0, timezone: "UTC")
            var digestCalls = 0
            fixture.coordinator.operations.applyConfig = { _ in throw ConfigSyncIncomplete.prefetched }
            fixture.coordinator.operations.applyDigests = { _, _ in digestCalls += 1 }
            fixture.coordinator.operations.fetchSchedules = { XCTFail("No refresh after config failure"); return [] }
            fixture.coordinator.operations.syncConfig = { XCTFail("No fallback on apply failure"); return false }
            await run(fixture.coordinator, force: force)
            XCTAssertEqual(issues(fixture.coordinator).map(\.component), [.configuration])
            XCTAssertTrue(issues(fixture.coordinator).first?.error is ConfigSyncIncomplete)
            XCTAssertEqual(digestCalls, 1)
            let schedule = try await fixture.settings.getGhostwriterSchedule()
            let enabled = try await fixture.settings.getEnabledPeriods()
            XCTAssertEqual(schedule?.morningHour, 7)
            XCTAssertEqual(enabled, [.morning])
            XCTAssertNil(fixture.coordinator.lastSyncTime)
        }
    }

    func testScheduleSaveAndDigestIngestionFailuresKeepSuccessfulSiblings() async throws {
        for force in [false, true] {
            let fixture = try await Fixture(now: fixedNow)
            var configCalls = 0
            fixture.coordinator.operations.applyConfig = { _ in configCalls += 1 }
            fixture.coordinator.operations.applyDigests = { _, _ in
                throw DigestSyncIngestionError(processedCount: 1, failedRemoteIds: ["retry"])
            }
            fixture.coordinator.operations.saveScheduleTimes = { _ in throw FixtureError.schedule }
            fixture.coordinator.operations.syncConfig = { XCTFail("No fallback on apply failure"); return false }
            await run(fixture.coordinator, force: force)
            XCTAssertEqual(Set(issues(fixture.coordinator).map(\.component)), [.digest, .schedule])
            XCTAssertEqual(configCalls, 1)
            let enabled = try await fixture.settings.getEnabledPeriods()
            XCTAssertEqual(enabled, [.morning])
            XCTAssertNil(fixture.coordinator.lastSyncTime)
        }
    }

    func testFeedOutcomesRemainVisibleAndPendingMutationSurvives() async throws {
        let errors: [FeedSyncV2Error] = [
            .partial(pending: 1, conflicts: 0, rejected: 0, phase: "push"),
            .failed(phase: "pull", message: "offline"), .upgradeRequired, .serverChanged
        ]
        for error in errors {
            let fixture = try await Fixture(now: fixedNow)
            let engine = IOSFeedV2StoreEngine(container: fixture.container)
            try engine.edit(url: "https://example.invalid/feed", title: "Pending", mode: .fidelity,
                            isEnabled: true, maxArticles: 2)
            var configCalls = 0
            fixture.coordinator.operations.feed = { _ in throw error }
            fixture.coordinator.operations.applyConfig = { _ in configCalls += 1 }
            await fixture.coordinator.performFullSync()
            XCTAssertEqual(issues(fixture.coordinator).map(\.component), [.feed])
            XCTAssertEqual(configCalls, 1)
            XCTAssertNil(fixture.coordinator.lastSyncTime)
            XCTAssertGreaterThan(try ModelContext(fixture.container).fetchCount(FetchDescriptor<FeedMutation>()), 0)
            if case .upgradeRequired = error {
                XCTAssertTrue(fixture.coordinator.requiresOlderServerFeedPreview)
            }
            if case .serverChanged = error {
                XCTAssertTrue(fixture.coordinator.requiresNewFeedBinding)
            }
        }
    }

    func testUnsupportedAndTransientFetchesRecoverThroughCompleteFallback() async throws {
        for force in [false, true] {
            for code in [404, 405, 503] {
                let fixture = try await Fixture(now: fixedNow)
                var events: [String] = []
                fixture.coordinator.operations.fetchCombined = { _, _ in
                    throw GhostwriterError.httpError(statusCode: code, message: nil)
                }
                fixture.coordinator.operations.syncConfig = { events.append("config"); return true }
                fixture.coordinator.operations.fetchSchedules = {
                    events.append("schedules"); return Fixture.schedule(hour: 8)
                }
                fixture.coordinator.operations.syncDigests = { _ in events.append("digest") }
                await run(fixture.coordinator, force: force)
                XCTAssertNil(fixture.coordinator.lastSyncError)
                XCTAssertEqual(fixture.coordinator.lastSyncTime, fixedNow)
                XCTAssertEqual(events, ["config", "schedules", "digest"])
            }
        }
    }

    func testFallbackFailuresRemainVisibleWithoutDroppingSuccessfulSiblings() async throws {
        for force in [false, true] {
            let fixture = try await Fixture(now: fixedNow)
            var digestCalls = 0
            fixture.coordinator.operations.fetchCombined = { _, _ in
                throw GhostwriterError.httpError(statusCode: 404, message: nil)
            }
            fixture.coordinator.operations.syncConfig = { false }
            fixture.coordinator.operations.saveEnabledPeriods = { _ in throw FixtureError.schedule }
            fixture.coordinator.operations.syncDigests = { _ in digestCalls += 1 }
            await run(fixture.coordinator, force: force)
            XCTAssertEqual(Set(issues(fixture.coordinator).map(\.component)),
                           [.combined, .configuration, .schedule])
            XCTAssertEqual(issues(fixture.coordinator).first?.phase, "unsupported endpoint")
            XCTAssertEqual(digestCalls, 1)
            XCTAssertNil(fixture.coordinator.lastSyncTime)
            XCTAssertFalse(fixture.coordinator.isSyncing)
        }
    }

    func testEveryFallbackComponentFailureAndTransientOriginAreVisible() async throws {
        for force in [false, true] {
            let fixture = try await Fixture(now: fixedNow)
            fixture.coordinator.operations.fetchCombined = { _, _ in
                throw GhostwriterError.httpError(statusCode: 503, message: "unavailable")
            }
            fixture.coordinator.operations.syncConfig = { throw FixtureError.config }
            fixture.coordinator.operations.fetchSchedules = { throw FixtureError.schedule }
            fixture.coordinator.operations.syncDigests = { _ in throw FixtureError.digest }
            await run(fixture.coordinator, force: force)
            XCTAssertEqual(Set(issues(fixture.coordinator).map(\.component)),
                           [.combined, .configuration, .schedule, .digest])
            XCTAssertEqual(issues(fixture.coordinator).first?.phase, "transport")
            XCTAssertNil(fixture.coordinator.lastSyncTime)
        }
    }

    func testNormalFallbackRespectsCadenceButForcedFallbackRunsDigest() async throws {
        let fixture = try await Fixture(now: fixedNow)
        try await fixture.settings.setLastDigestSyncTime(fixedNow)
        fixture.coordinator.operations.fetchCombined = { _, _ in
            throw GhostwriterError.httpError(statusCode: 405, message: nil)
        }
        var digestCalls = 0
        fixture.coordinator.operations.syncDigests = { _ in digestCalls += 1 }
        await fixture.coordinator.performFullSync()
        XCTAssertEqual(digestCalls, 0)
        await fixture.coordinator.performFullSyncIncludingDigests()
        XCTAssertEqual(digestCalls, 1)
        XCTAssertNil(fixture.coordinator.lastSyncError)
    }

    func testReadFailuresAreVisibleAndDoNotTriggerFallback() async throws {
        let fixture = try await Fixture(now: fixedNow)
        var configCalls = 0
        fixture.coordinator.operations.applyConfig = { _ in configCalls += 1 }
        fixture.coordinator.operations.lastDigestSync = { throw FixtureError.read }
        await fixture.coordinator.performFullSync()
        XCTAssertEqual(issues(fixture.coordinator).map(\.component), [.settings])
        XCTAssertEqual(configCalls, 1)
        fixture.coordinator.operations.lastDigestSync = { nil }
        fixture.coordinator.operations.knownDigestIDs = { throw FixtureError.read }
        fixture.coordinator.operations.fetchCombined = { since, ids in
            XCTAssertEqual(since, "2026-09-27T10:00:00Z".toISO8601Date())
            XCTAssertEqual(ids, [])
            return try Fixture.response()
        }
        fixture.coordinator.operations.syncConfig = { XCTFail("Read error must not trigger fallback"); return false }
        await fixture.coordinator.performFullSyncIncludingDigests()
        XCTAssertEqual(issues(fixture.coordinator).map(\.component), [.digest])
        XCTAssertEqual(configCalls, 2)
        XCTAssertNil(fixture.coordinator.lastSyncTime)
    }

    func testRecentEmptyCombinedThenNewPayloadStillIngests() async throws {
        let fixture = try await Fixture(now: fixedNow)
        try await fixture.settings.setLastDigestSyncTime(fixedNow)
        var responseDigests = "[]"
        var ingestCalls = 0
        fixture.coordinator.operations.fetchCombined = { _, _ in
            try Fixture.response(digests: responseDigests)
        }
        fixture.coordinator.operations.applyDigests = { values, _ in
            ingestCalls += 1
            XCTAssertEqual(values.count, 1)
        }
        await fixture.coordinator.performFullSync()
        XCTAssertEqual(ingestCalls, 0)
        XCTAssertNil(fixture.coordinator.lastSyncError)
        responseDigests = """
        [{"id":"new","filename":"new.epub","period":"morning","status":"completed",
          "article_count":0,"created_at":"2026-09-27T00:00:00Z","articles":[]}]
        """
        await fixture.coordinator.performFullSync()
        XCTAssertEqual(ingestCalls, 1)
        XCTAssertNil(fixture.coordinator.lastSyncError)
    }

    func testPrivateCombinedCursorDoesNotClaimFeedSuccessAndResetsForDestination() async throws {
        let fixture = try await Fixture(now: fixedNow)
        var cursors: [Date?] = []
        fixture.coordinator.operations.fetchCombined = { since, _ in
            cursors.append(since)
            return try Fixture.response()
        }
        await fixture.coordinator.performFullSync()
        await fixture.coordinator.performFullSync()
        let expected = "2026-09-27T10:00:00Z".toISO8601Date()
        XCTAssertNil(cursors[0])
        XCTAssertEqual(cursors[1], expected)
        let visibleFeedSuccess = try await fixture.settings.getLastFeedSyncTime()
        XCTAssertNil(visibleFeedSuccess)

        try await fixture.settings.setGhostwriterURL("https://other.invalid")
        await fixture.coordinator.performFullSync()
        XCTAssertNil(cursors[2])
        XCTAssertNil(fixture.coordinator.lastSyncError)
    }

    func testMalformedCombinedTimestampAndFetchFailureDoNotBlockOtherWork() async throws {
        let fixture = try await Fixture(now: fixedNow)
        var cursors: [Date?] = []
        var configCalls = 0
        fixture.coordinator.operations.applyConfig = { _ in configCalls += 1 }
        fixture.coordinator.operations.fetchCombined = { since, _ in
            cursors.append(since)
            return try Fixture.response(serverTimestamp: "bad timestamp")
        }
        await fixture.coordinator.performFullSync()
        await fixture.coordinator.performFullSync()
        XCTAssertEqual(cursors.count, 2)
        XCTAssertTrue(cursors.allSatisfy { $0 == nil })
        XCTAssertEqual(configCalls, 2)
        XCTAssertNil(fixture.coordinator.lastSyncError)

        fixture.coordinator.operations.fetchCombined = { _, _ in throw FixtureError.read }
        await fixture.coordinator.performFullSync()
        XCTAssertNil(fixture.coordinator.lastSyncError)
        XCTAssertEqual(fixture.coordinator.lastSyncTime, fixedNow)
    }

    func testScheduleFetchFailureAndAllDigestFailureRetainPriorSuccessTime() async throws {
        let fixture = try await Fixture(now: fixedNow)
        await fixture.coordinator.performFullSync()
        let prior = fixture.coordinator.lastSyncTime
        let next = fixedNow.addingTimeInterval(60)
        fixture.coordinator.now = { next }
        fixture.coordinator.operations.fetchSchedules = { throw FixtureError.schedule }
        fixture.coordinator.operations.applyDigests = { _, _ in
            throw DigestSyncIngestionError(processedCount: 0, failedRemoteIds: ["one", "two"])
        }
        fixture.coordinator.operations.syncConfig = { XCTFail("No fallback after apply"); return false }
        await fixture.coordinator.performFullSyncIncludingDigests()
        XCTAssertEqual(Set(issues(fixture.coordinator).map(\.component)), [.digest, .schedule])
        XCTAssertEqual(fixture.coordinator.lastSyncTime, prior)
    }

    func testEnabledSaveFailureRemainsVisibleWhenConfigIsPending() async throws {
        let fixture = try await Fixture(now: fixedNow)
        fixture.coordinator.operations.applyConfig = { _ in throw ConfigSyncIncomplete.prefetched }
        fixture.coordinator.operations.saveEnabledPeriods = { _ in throw FixtureError.schedule }
        fixture.coordinator.operations.saveScheduleTimes = { _ in XCTFail("Pending times must not be saved") }
        await fixture.coordinator.performFullSyncIncludingDigests()
        XCTAssertEqual(Set(issues(fixture.coordinator).map(\.component)),
                       [.configuration, .schedule])
        XCTAssertNil(fixture.coordinator.lastSyncTime)
    }

    func testNormalCadenceSkipsDigestButForcedRunInvokesIt() async throws {
        let fixture = try await Fixture(now: fixedNow)
        try await fixture.settings.setLastDigestSyncTime(fixedNow)
        var digestCalls = 0
        fixture.coordinator.operations.applyDigests = { _, _ in digestCalls += 1 }
        await fixture.coordinator.performFullSync()
        XCTAssertEqual(digestCalls, 0)
        await fixture.coordinator.performFullSyncIncludingDigests()
        XCTAssertEqual(digestCalls, 1)
        XCTAssertNil(fixture.coordinator.lastSyncError)
    }

    func testUnconfiguredAndConfigurationReadFailureAreDistinct() async throws {
        let fixture = try await Fixture(now: fixedNow)
        fixture.coordinator.operations.configured = { false }
        await fixture.coordinator.performFullSync()
        XCTAssertNil(fixture.coordinator.lastSyncError)
        XCTAssertNil(fixture.coordinator.lastSyncTime)
        fixture.coordinator.operations.configured = { throw FixtureError.read }
        await fixture.coordinator.performFullSyncIncludingDigests()
        XCTAssertEqual(issues(fixture.coordinator).map(\.component), [.settings])
        XCTAssertNil(fixture.coordinator.lastSyncTime)
        XCTAssertFalse(fixture.coordinator.isSyncing)
    }

    func testCancellationStopsLaterPhasesAndPreservesPreviousSuccess() async throws {
        for phase in ["feed", "fetch", "apply", "fallback"] {
            let fixture = try await Fixture(now: fixedNow)
            await fixture.coordinator.performFullSync()
            var events: [String] = []
            switch phase {
            case "feed":
                fixture.coordinator.operations.feed = { _ in
                    events.append("feed"); withUnsafeCurrentTask { $0?.cancel() }
                }
            case "fetch":
                fixture.coordinator.operations.fetchCombined = { _, _ in
                    events.append("fetch"); withUnsafeCurrentTask { $0?.cancel() }
                    return try Fixture.response()
                }
            case "apply":
                fixture.coordinator.operations.applyConfig = { _ in
                    events.append("apply"); withUnsafeCurrentTask { $0?.cancel() }
                }
            default:
                fixture.coordinator.operations.fetchCombined = { _, _ in
                    throw GhostwriterError.httpError(statusCode: 404, message: nil)
                }
                fixture.coordinator.operations.syncConfig = {
                    events.append("fallback"); withUnsafeCurrentTask { $0?.cancel() }
                    return true
                }
            }
            fixture.coordinator.operations.syncDigests = { _ in events.append("later digest") }
            let task = Task { await fixture.coordinator.performFullSyncIncludingDigests() }
            await task.value
            XCTAssertEqual(fixture.coordinator.lastSyncTime, fixedNow)
            XCTAssertFalse(fixture.coordinator.isSyncing)
            XCTAssertNotNil(fixture.coordinator.lastSyncError)
            XCTAssertFalse(events.contains("later digest"))
            XCTAssertEqual(events.count, 1)
        }
    }

    func testActualPartialDigestRetryKeepsIdentityAndOverallSuccessPending() async throws {
        let fixture = try await Fixture(now: fixedNow)
        try await fixture.settings.setGhostwriterDownloadEpubsOnSync(true)
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        var fail = true
        let service = try DigestSyncService(settingsRepository: fixture.settings,
            digestRepository: fixture.digests, digestsDirectory: directory,
            plan: { .notConfigured },
            download: { filename in
                if filename == "retry.epub" && fail { throw FixtureError.download }
                return Data("epub".utf8)
            }, articles: { _ in [] })
        let digests = """
        [{"id":"ok","filename":"ok.epub","period":"morning","status":"completed",
          "article_count":1,"created_at":"2026-09-27T00:00:00Z",
          "articles":[{"id":"article-ok","title":"Title","url":"https://example.invalid/ok",
                       "mode":"fidelity","word_count":4,"content":"Body","feed_title":"Feed",
                       "sort_order":0,"ai_failed":false}]},
         {"id":"retry","filename":"retry.epub","period":"morning","status":"completed",
          "article_count":1,"created_at":"2026-09-27T00:00:00Z",
          "articles":[{"id":"article-retry","title":"Title","url":"https://example.invalid/retry",
                       "mode":"fidelity","word_count":4,"content":"Body","feed_title":"Feed",
                       "sort_order":0,"ai_failed":false}]}]
        """
        fixture.coordinator.operations.fetchCombined = { _, _ in try Fixture.response(digests: digests) }
        fixture.coordinator.operations.applyDigests = { values, tracker in
            try await service.processDigestsFromSync(values, tracker: tracker)
        }
        await fixture.coordinator.performFullSyncIncludingDigests()
        XCTAssertEqual(issues(fixture.coordinator).map(\.component), [.digest])
        XCTAssertNil(fixture.coordinator.lastSyncTime)
        let firstIDs = try await fixture.digests.getAllRemoteIds()
        XCTAssertEqual(firstIDs, ["ok"])
        fail = false
        await fixture.coordinator.performFullSyncIncludingDigests()
        XCTAssertNil(fixture.coordinator.lastSyncError)
        let finalIDs = try await fixture.digests.getAllRemoteIds()
        let finalCount = try await fixture.digests.getDigestCount()
        XCTAssertEqual(Set(finalIDs), ["ok", "retry"])
        XCTAssertEqual(finalCount, 2)
        XCTAssertEqual(fixture.coordinator.lastSyncTime, fixedNow)
    }
}
