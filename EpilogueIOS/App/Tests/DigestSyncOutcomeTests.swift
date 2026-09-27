import Foundation
import SwiftData
import XCTest
import Domain
import Data
import GhostwriterClient
@testable import Epilogue

@MainActor
final class DigestSyncOutcomeTests: XCTestCase {
    private enum FixtureError: Error { case download, articles }

    @MainActor private struct Fixture {
        let container: ModelContainer
        let repository: DigestRepository
        let settings: SettingsRepository
        let directory: URL

        init(download: Bool = false) async throws {
            let schema = Schema([Feed.self, Digest.self, DigestArticle.self])
            container = try ModelContainer(
                for: schema,
                configurations: ModelConfiguration(isStoredInMemoryOnly: true)
            )
            repository = DigestRepository(modelContext: ModelContext(container), maxDigests: 30)
            let defaults = UserDefaults(suiteName: "digest-sync-test-\(UUID().uuidString)")!
            settings = SettingsRepository(userDefaults: defaults)
            try await settings.setGhostwriterEnabled(true)
            try await settings.setGhostwriterURL("https://example.invalid")
            try await settings.setGhostwriterDownloadEpubsOnSync(download)
            directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        }

        func service(
            plan: @escaping @MainActor () async throws -> SharedDigestSyncPlan = { .notConfigured },
            download: @escaping @MainActor (String) async throws -> Data = { _ in Data("epub".utf8) },
            articles: @escaping @MainActor (String) async throws -> [DigestArticleData] = { _ in [] }
        ) throws -> DigestSyncService {
            try DigestSyncService(
                settingsRepository: settings,
                digestRepository: repository,
                digestsDirectory: directory,
                plan: plan,
                download: download,
                articles: articles
            )
        }
    }

    private func combined(_ id: String) -> SharedDigestSyncPlan.CombinedDigest {
        .init(id: id, filename: "\(id).epub", period: "morning", articleCount: 1,
              createdAt: "2026-09-27T00:00:00Z", completedAt: nil,
              articles: [.init(id: "article-\(id)", title: "Title", url: "https://example.invalid/\(id)",
                               mode: "fidelity", wordCount: 4, content: "Body", contentHTML: nil,
                               author: nil, feedTitle: "Feed", sortOrder: 0)])
    }

    private func legacy(_ id: String, articleCount: Int = 1) -> SharedDigestSyncPlan.LegacyDigest {
        .init(id: id, filename: "\(id).epub", period: "morning", articleCount: articleCount,
              createdAt: "2026-09-27T00:00:00Z", completedAt: nil)
    }

    private func synced(_ id: String) throws -> SyncDigest {
        let json = """
        {"id":"\(id)","filename":"\(id).epub","period":"morning","status":"completed",
         "article_count":0,"created_at":"2026-09-27T00:00:00Z","articles":[]}
        """
        return try JSONDecoder().decode(SyncDigest.self, from: Data(json.utf8))
    }

    func testCombinedPartialFailureKeepsPriorTimestampAndRetryDoesNotDuplicateSibling() async throws {
        let fixture = try await Fixture(download: true)
        let prior = Date(timeIntervalSince1970: 1_700_000_000)
        try await fixture.settings.setLastDigestSyncTime(prior)
        var fail = true
        var downloads: [String] = []
        let service = try fixture.service(
            plan: { [self] in .combined(digests: [combined("ok"), combined("retry")], shouldDownloadEpubs: true) },
            download: { filename in
                downloads.append(filename)
                if filename == "retry.epub" && fail { throw FixtureError.download }
                return Data("epub".utf8)
            }
        )
        do {
            try await service.sync()
            XCTFail("Expected partial ingestion error")
        } catch let error as DigestSyncIngestionError {
            XCTAssertEqual(error.processedCount, 1)
            XCTAssertEqual(error.failedRemoteIds, ["retry"])
        }
        let observed88 = try await fixture.settings.getLastDigestSyncTime()
        XCTAssertEqual(observed88, prior)
        let observed90 = try await fixture.repository.getAllRemoteIds()
        XCTAssertEqual(observed90, ["ok"])

        fail = false
        try await service.sync()
        let observed95 = try await fixture.repository.getAllRemoteIds()
        XCTAssertEqual(Set(observed95), ["ok", "retry"])
        let observed97 = try await fixture.repository.getDigestCount()
        XCTAssertEqual(observed97, 2)
        XCTAssertEqual(downloads.filter { $0 == "ok.epub" }.count, 1)
        let observed100 = try await fixture.settings.getLastDigestSyncTime()
        XCTAssertNotEqual(observed100, prior)
    }

    func testZeroArticleCombinedDigestIsIndexedWithoutEpubDownload() async throws {
        let fixture = try await Fixture(download: true)
        let prior = Date(timeIntervalSince1970: 1_700_000_000)
        try await fixture.settings.setLastDigestSyncTime(prior)
        let service = try fixture.service(
            download: { _ in XCTFail("Zero-article digest has no EPUB"); throw FixtureError.download }
        )
        try await service.processDigestsFromSync([synced("empty")])
        try await service.processDigestsFromSync([synced("empty")])
        let ids = try await fixture.repository.getAllRemoteIds()
        let count = try await fixture.repository.getDigestCount()
        let lastSync = try await fixture.settings.getLastDigestSyncTime()
        XCTAssertEqual(ids, ["empty"])
        XCTAssertEqual(count, 1)
        XCTAssertNotEqual(lastSync, prior)
        let stored = try await fixture.repository.getDigestByRemoteId("empty")
        XCTAssertEqual(stored?.epubFilePath, "")
    }

    func testZeroArticleLegacyDigestIsIndexedAfterEmptyArticleFetch() async throws {
        let fixture = try await Fixture(download: true)
        var articleCalls = 0
        let service = try fixture.service(
            plan: { [self] in .legacy(digests: [legacy("empty-legacy", articleCount: 0)],
                                       shouldDownloadEpubs: true) },
            download: { _ in XCTFail("Zero-article digest has no EPUB"); throw FixtureError.download },
            articles: { _ in articleCalls += 1; return [] }
        )
        try await service.sync()
        let ids = try await fixture.repository.getAllRemoteIds()
        let lastSync = try await fixture.settings.getLastDigestSyncTime()
        XCTAssertEqual(ids, ["empty-legacy"])
        XCTAssertEqual(articleCalls, 1)
        XCTAssertNotNil(lastSync)
        let stored = try await fixture.repository.getDigestByRemoteId("empty-legacy")
        XCTAssertEqual(stored?.epubFilePath, "")
    }

    func testRemoteArtifactEligibilityRequiresNonemptyDigestAndRealLocalFile() {
        let empty = Digest(epubFilePath: "", articleCount: 0, triggerType: .ghostwriter,
                           isComplete: true, remoteId: "empty")
        let indexed = Digest(epubFilePath: "", articleCount: 1, triggerType: .ghostwriter,
                             isComplete: true, remoteId: "indexed")
        XCTAssertFalse(DigestArtifactEligibility.canDownloadRemoteFile(empty))
        XCTAssertFalse(DigestArtifactEligibility.hasLocalEPUB(empty))
        XCTAssertTrue(DigestArtifactEligibility.canDownloadRemoteFile(indexed))
        XCTAssertFalse(DigestArtifactEligibility.hasLocalEPUB(indexed))
    }

    func testRepeatedPayloadForIndexedDigestRetriesDownloadAndUpdatesArtifactPath() async throws {
        let fixture = try await Fixture(download: false)
        let plan: @MainActor () async throws -> SharedDigestSyncPlan = { [self] in
            .combined(digests: [combined("indexed")], shouldDownloadEpubs: false)
        }
        var fail = true
        var downloads = 0
        let service = try fixture.service(plan: plan, download: { _ in
            downloads += 1
            if fail { throw FixtureError.download }
            return Data("epub".utf8)
        })
        try await service.sync()
        let indexed = try await fixture.repository.getDigestByRemoteId("indexed")
        XCTAssertNotNil(indexed)
        XCTAssertFalse(FileManager.default.fileExists(atPath: indexed!.epubFilePath))

        try await fixture.settings.setGhostwriterDownloadEpubsOnSync(true)
        do {
            try await service.sync()
            XCTFail("Expected download failure")
        } catch is DigestSyncIngestionError {}
        XCTAssertEqual(downloads, 1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: indexed!.epubFilePath))

        fail = false
        try await service.sync()
        XCTAssertEqual(downloads, 2)
        XCTAssertTrue(FileManager.default.fileExists(atPath: indexed!.epubFilePath))
        let count = try await fixture.repository.getDigestCount()
        XCTAssertEqual(count, 1)
    }

    func testDirectCombinedAllFailuresAndEmptySuccess() async throws {
        let fixture = try await Fixture(download: false)
        let prior = Date(timeIntervalSince1970: 1_700_000_000)
        try await fixture.settings.setLastDigestSyncTime(prior)
        let service = try fixture.service()
        do {
            try await service.processDigestsFromSync([synced("../bad"), synced("nested/bad")])
            XCTFail("Expected all-failed ingestion error")
        } catch let error as DigestSyncIngestionError {
            XCTAssertEqual(error.processedCount, 0)
            XCTAssertEqual(Set(error.failedRemoteIds), ["../bad", "nested/bad"])
        }
        let observed116 = try await fixture.repository.getDigestCount()
        XCTAssertEqual(observed116, 0)
        let observed118 = try await fixture.settings.getLastDigestSyncTime()
        XCTAssertEqual(observed118, prior)

        try await service.processDigestsFromSync([])
        let observed122 = try await fixture.settings.getLastDigestSyncTime()
        XCTAssertNotEqual(observed122, prior)
    }

    func testIndexingOnlySavesWithoutDownload() async throws {
        let fixture = try await Fixture(download: false)
        let service = try fixture.service(
            plan: { [self] in .combined(digests: [combined("index")], shouldDownloadEpubs: false) },
            download: { _ in XCTFail("Indexing must not download"); throw FixtureError.download }
        )
        try await service.sync()
        let stored = try await fixture.repository.getDigestByRemoteId("index")
        XCTAssertNotNil(stored)
        XCTAssertFalse(FileManager.default.fileExists(atPath: stored!.epubFilePath))
    }

    func testPlannedCombinedReportsFileAndDownloadFailuresTogether() async throws {
        let fixture = try await Fixture(download: true)
        let service = try fixture.service(
            plan: { [self] in
                .combined(digests: [combined("good"), combined("../invalid"), combined("offline")],
                          shouldDownloadEpubs: true)
            },
            download: { filename in
                if filename == "offline.epub" { throw FixtureError.download }
                return Data("epub".utf8)
            }
        )
        do {
            try await service.sync()
            XCTFail("Expected partial ingestion error")
        } catch let error as DigestSyncIngestionError {
            XCTAssertEqual(error.processedCount, 1)
            XCTAssertEqual(Set(error.failedRemoteIds), ["../invalid", "offline"])
        }
        let known = try await fixture.repository.getAllRemoteIds()
        XCTAssertEqual(known, ["good"])
    }

    func testLegacyArticleFetchFailureDoesNotRecordRemoteIdAndRetries() async throws {
        let fixture = try await Fixture(download: false)
        var fail = true
        let article = DigestArticleData(id: "article", title: "Title", url: "https://example.invalid/a",
                                        mode: "fidelity", wordCount: 4, content: "Body",
                                        author: nil, feedTitle: "Feed", sortOrder: 0)
        let service = try fixture.service(
            plan: { [self] in .legacy(digests: [legacy("legacy")], shouldDownloadEpubs: false) },
            articles: { _ in
                if fail { throw FixtureError.articles }
                return [article]
            }
        )
        do {
            try await service.sync()
            XCTFail("Expected fetch failure")
        } catch is DigestSyncIngestionError {}
        let observed155 = try await fixture.repository.getAllRemoteIds().isEmpty
        XCTAssertTrue(observed155)
        fail = false
        try await service.sync()
        let observed159 = try await fixture.repository.getDigestByRemoteId("legacy")?.articles.count
        XCTAssertEqual(observed159, 1)
    }

    func testCancellationStopsFurtherSchedulingAndDoesNotAdvanceTimestamp() async throws {
        let fixture = try await Fixture(download: true)
        let prior = Date(timeIntervalSince1970: 1_700_000_000)
        try await fixture.settings.setLastDigestSyncTime(prior)
        var started: [String] = []
        let service = try fixture.service(
            plan: { [self] in .combined(digests: [combined("a"), combined("b"), combined("c"), combined("d")], shouldDownloadEpubs: true) },
            download: { filename in
                started.append(filename)
                throw CancellationError()
            }
        )
        do {
            try await service.sync()
            XCTFail("Expected cancellation")
        } catch is CancellationError {}
        XCTAssertLessThanOrEqual(started.count, 3)
        let observed180 = try await fixture.repository.getDigestCount()
        XCTAssertEqual(observed180, 0)
        let observed182 = try await fixture.settings.getLastDigestSyncTime()
        XCTAssertEqual(observed182, prior)
    }
}
