//
//  DigestGeneratorTests.swift
//  Epilogue
//
//  Created on 2026-02-03.
//

import Testing
import Foundation
@testable import Data
@testable import Domain

@Suite("DigestGenerator Tests")
struct DigestGeneratorTests {
    @Test("Generate digest throws when no enabled feeds")
    func testNoEnabledFeeds() async throws {
        let feedRepository = StubFeedRepository(enabledFeeds: [])
        let digestRepository = StubDigestRepository()
        let articleRepository = StubArticleRepository(articlesByFeed: [:])
        let epubBuilder = StubEPUBBuilder(data: Data([0x1]))

        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)

        let generator = DigestGenerator(
            feedRepository: feedRepository,
            digestRepository: digestRepository,
            articleRepository: articleRepository,
            epubBuilder: epubBuilder,
            documentsDirectory: tempDir
        )

        do {
            _ = try await generator.generateDigest(triggerType: .manual)
            #expect(false, "Expected error")
        } catch {
            #expect(error.localizedDescription.contains("No enabled feeds"))
        }

        let updated = await digestRepository.lastUpdatedDigest()
        #expect(updated?.isComplete == false)
        #expect(updated?.errorMessage?.contains("No enabled feeds") == true)
    }

    @Test("Generate digest throws when no articles found")
    func testNoArticlesFound() async throws {
        let feed = Feed(url: "https://example.com/feed", name: "Feed", mode: .fidelity)
        let feedRepository = StubFeedRepository(enabledFeeds: [feed])
        let digestRepository = StubDigestRepository()
        let articleRepository = StubArticleRepository(articlesByFeed: [feed.url: []])
        let epubBuilder = StubEPUBBuilder(data: Data([0x1]))

        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)

        let generator = DigestGenerator(
            feedRepository: feedRepository,
            digestRepository: digestRepository,
            articleRepository: articleRepository,
            epubBuilder: epubBuilder,
            documentsDirectory: tempDir
        )

        do {
            _ = try await generator.generateDigest(triggerType: .manual)
            #expect(false, "Expected error")
        } catch {
            #expect(error.localizedDescription.contains("No articles"))
        }

        let updated = await digestRepository.lastUpdatedDigest()
        #expect(updated?.isComplete == false)
        #expect(updated?.errorMessage?.contains("No articles") == true)
    }

    @Test("Generate digest succeeds with article counts and file size")
    func testGenerateDigestSuccess() async throws {
        let feed = Feed(url: "https://example.com/feed", name: "Feed", mode: .fidelity)
        let feedRepository = StubFeedRepository(enabledFeeds: [feed])
        let digestRepository = StubDigestRepository()

        let articles = [
            ProcessedArticle(
                title: "Summary",
                author: "",
                content: "<p>Summary</p>",
                originalUrl: "https://example.com/summary",
                feedUrl: feed.url,
                feedName: feed.name,
                isSummary: true,
                wordCount: 5
            ),
            ProcessedArticle(
                title: "Deep Dive",
                author: "",
                content: "<p>Deep Dive</p>",
                originalUrl: "https://example.com/deep",
                feedUrl: feed.url,
                feedName: feed.name,
                isSummary: false,
                wordCount: 10
            )
        ]

        let articleRepository = StubArticleRepository(articlesByFeed: [feed.url: articles])
        let epubBuilder = StubEPUBBuilder(data: Data([0x1, 0x2, 0x3]))

        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)

        let generator = DigestGenerator(
            feedRepository: feedRepository,
            digestRepository: digestRepository,
            articleRepository: articleRepository,
            epubBuilder: epubBuilder,
            documentsDirectory: tempDir
        )

        let digest = try await generator.generateDigest(triggerType: .manual)

        #expect(digest.isComplete == true)
        #expect(digest.articleCount == 2)
        #expect(digest.briefingCount == 1)
        #expect(digest.deepDiveCount == 1)
        #expect(digest.fileSizeBytes == 3)
        #expect(digest.articles.count == 2)

        try? FileManager.default.removeItem(at: tempDir)
    }
}

private final class StubFeedRepository: FeedRepositoryProtocol, @unchecked Sendable {
    private let enabledFeeds: [Feed]

    init(enabledFeeds: [Feed]) {
        self.enabledFeeds = enabledFeeds
    }

    func getAllFeeds() async throws -> [Feed] { enabledFeeds }
    func getEnabledFeeds() async throws -> [Feed] { enabledFeeds }
    func getFeed(url: String) async throws -> Feed? { enabledFeeds.first { $0.url == url } }
    func addFeed(_ feed: Feed) async throws {}
    func updateFeed(_ feed: Feed) async throws {}
    func deleteFeed(url: String) async throws {}
    func updateLastFetched(url: String, timestamp: Int64) async throws {}
    func feedExists(url: String) async throws -> Bool { enabledFeeds.contains { $0.url == url } }
    func upsertAll(_ feeds: [Feed]) async throws {}
    func deleteByURLs(_ urls: [String]) async throws {}
    func clearAllLocallyModified() async throws {}
    func getLocallyModifiedFeeds() async throws -> [Feed] { [] }
    func markAsLocallyModified(url: String) async throws {}
}

private final class StubDigestRepository: DigestRepositoryProtocol, @unchecked Sendable {
    private var created: [Digest] = []
    private var updated: [Digest] = []

    func getAllDigests() async throws -> [Digest] { updated.isEmpty ? created : updated }
    func getDigest(id: UUID) async throws -> Digest? { (updated + created).first { $0.id == id } }
    func createDigest(_ digest: Digest) async throws { created.append(digest) }
    func updateDigest(_ digest: Digest) async throws { updated.append(digest) }
    func deleteDigest(id: UUID) async throws {}
    func deleteDigests(ids: [UUID]) async throws {}
    func getDigests(from startDate: Date, to endDate: Date) async throws -> [Digest] { [] }
    func getDigestCount() async throws -> Int { (updated.isEmpty ? created : updated).count }
    func enforceRetentionPolicy(maxDigests: Int) async throws {}
    func getAllRemoteIds() async throws -> [String] { [] }
    func getDigestByRemoteId(_ remoteId: String) async throws -> Digest? { nil }

    func saveRemoteDigest(
        remoteId: String,
        epubFilePath: String,
        articleCount: Int,
        generatedAt: Date,
        period: String,
        articles: [DigestArticleData]?
    ) async throws -> Digest {
        Digest(
            generatedAt: generatedAt,
            epubFilePath: epubFilePath,
            articleCount: articleCount,
            briefingCount: 0,
            deepDiveCount: 0,
            triggerType: .ghostwriter,
            isComplete: true,
            remoteId: remoteId,
            period: period
        )
    }

    func lastUpdatedDigest() -> Digest? {
        updated.last
    }
}

private final class StubArticleRepository: ArticleRepositoryProtocol, @unchecked Sendable {
    private let articlesByFeed: [String: [ProcessedArticle]]

    init(articlesByFeed: [String: [ProcessedArticle]]) {
        self.articlesByFeed = articlesByFeed
    }

    func fetchAndProcessArticles() async throws -> [ProcessedArticle] {
        articlesByFeed.values.flatMap { $0 }
    }

    func fetchAndProcessArticles(from feed: Feed) async throws -> [ProcessedArticle] {
        articlesByFeed[feed.url] ?? []
    }

    func fetchFeedArticles(feedUrl: String) async throws -> [RawArticle] { [] }
    func processArticle(_ article: RawArticle, mode: ProcessingMode) async throws -> ProcessedArticle {
        throw ArticleProcessingError.aiServiceUnavailable
    }

    func extractFullContent(url: String) async throws -> String { "" }
    func validateFeedUrl(_ url: String) async throws -> Bool { true }
}

private struct StubEPUBBuilder: EPUBBuilderProtocol {
    let data: Data

    func generateEPUB(articles: [ProcessedArticle], outputPath: String, date: Date) throws -> URL {
        let url = URL(fileURLWithPath: outputPath)
        let directory = url.deletingLastPathComponent()
        if !FileManager.default.fileExists(atPath: directory.path) {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        }
        try data.write(to: url)
        return url
    }
}
