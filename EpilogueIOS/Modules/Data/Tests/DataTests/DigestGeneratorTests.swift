//
//  DigestGeneratorTests.swift
//  Epilogue
//

import Testing
import Foundation
import SwiftData
@testable import Data
@testable import Domain

@Suite("DigestGenerator Tests")
@MainActor
struct DigestGeneratorTests {
    @Test("Generate digest uses unique EPUB filenames across repeated same-day runs")
    func testUniqueFileNamesAcrossRuns() async throws {
        let schema = Schema([Feed.self, Digest.self, DigestArticle.self])
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: schema, configurations: config)
        let context = ModelContext(container)

        let digestRepository = DigestRepository(modelContext: context, maxDigests: 30)
        let feedRepository = MockFeedRepository(
            enabledFeeds: [
                Feed(
                    url: "https://example.com/rss",
                    name: "Example Feed",
                    mode: .fidelity,
                    isEnabled: true
                )
            ]
        )
        let articleRepository = MockArticleRepository()
        let epubBuilder = MockEPUBBuilder()

        let tempDir = FileManager.default.temporaryDirectory.appendingPathComponent(
            "epilogue-digest-generator-tests-\(UUID().uuidString)"
        )
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let generator = DigestGenerator(
            feedRepository: feedRepository,
            digestRepository: digestRepository,
            articleRepository: articleRepository,
            epubBuilder: epubBuilder,
            documentsDirectory: tempDir
        )

        let first = try await generator.generateDigest(triggerType: .scheduled)
        let second = try await generator.generateDigest(triggerType: .scheduled)

        #expect(first.epubFilePath != second.epubFilePath)
        #expect(FileManager.default.fileExists(atPath: first.epubFilePath))
        #expect(FileManager.default.fileExists(atPath: second.epubFilePath))
    }
}

private final class MockFeedRepository: FeedRepositoryProtocol, @unchecked Sendable {
    private var enabledFeeds: [Feed]

    init(enabledFeeds: [Feed]) {
        self.enabledFeeds = enabledFeeds
    }

    func getAllFeeds() async throws -> [Feed] { enabledFeeds }

    func getEnabledFeeds() async throws -> [Feed] {
        enabledFeeds.filter(\.isEnabled)
    }

    func getFeed(url: String) async throws -> Feed? {
        enabledFeeds.first { $0.url == url }
    }

    func addFeed(_ feed: Feed) async throws {
        enabledFeeds.append(feed)
    }

    func updateFeed(_ feed: Feed) async throws {
        guard let index = enabledFeeds.firstIndex(where: { $0.url == feed.url }) else { return }
        enabledFeeds[index] = feed
    }

    func deleteFeed(url: String) async throws {
        enabledFeeds.removeAll { $0.url == url }
    }

    func updateLastFetched(url: String, timestamp: Int64) async throws {
        guard let feed = enabledFeeds.first(where: { $0.url == url }) else { return }
        feed.lastFetched = timestamp
    }

    func feedExists(url: String) async throws -> Bool {
        enabledFeeds.contains { $0.url == url }
    }

    func upsertAll(_ feeds: [Feed]) async throws {
        enabledFeeds = feeds
    }

    func deleteByURLs(_ urls: [String]) async throws {
        enabledFeeds.removeAll { urls.contains($0.url) }
    }

    func clearAllLocallyModified() async throws {}

    func getLocallyModifiedFeeds() async throws -> [Feed] { [] }

    func markAsLocallyModified(url: String) async throws {}
}

private struct MockArticleRepository: ArticleRepositoryProtocol {
    func fetchAndProcessArticles() async throws -> [ProcessedArticle] {
        [sampleArticle]
    }

    func fetchAndProcessArticles(from feed: Feed) async throws -> [ProcessedArticle] {
        [
            ProcessedArticle(
                title: "Article from \(feed.name)",
                content: "<p>Hello world</p>",
                originalUrl: "https://example.com/articles/1",
                feedUrl: feed.url,
                feedName: feed.name,
                isSummary: false,
                wordCount: 200
            )
        ]
    }

    func fetchFeedArticles(feedUrl: String) async throws -> [RawArticle] { [] }

    func processArticle(_ article: RawArticle, mode: ProcessingMode) async throws -> ProcessedArticle {
        sampleArticle
    }

    func extractFullContent(url: String) async throws -> String { "<p>content</p>" }

    func validateFeedUrl(_ url: String) async throws -> Bool { true }

    private var sampleArticle: ProcessedArticle {
        ProcessedArticle(
            title: "Sample",
            content: "<p>Sample</p>",
            originalUrl: "https://example.com/sample",
            feedUrl: "https://example.com/rss",
            feedName: "Example Feed",
            isSummary: false,
            wordCount: 120
        )
    }
}

private struct MockEPUBBuilder: EPUBBuilderProtocol {
    func generateEPUB(articles: [ProcessedArticle], outputPath: String, date: Date) throws -> URL {
        let url = URL(fileURLWithPath: outputPath)
        let payload = Data("EPUB".utf8)
        try payload.write(to: url)
        return url
    }
}
