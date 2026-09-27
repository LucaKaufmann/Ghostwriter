import Foundation
import SwiftData
import Testing
import Domain
@testable import Data

@Suite("Incremental local generation")
@MainActor
struct DeliveryGenerationTests {
    private func setup(maxArticles: Int, links: [String],
                       failed: Set<String> = [], filtered: Set<String> = [],
                       fetchFails: Bool = false) throws -> (DigestGenerator, FixtureArticles, ModelContainer, URL) {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("delivery-generator-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
        let configuration = ModelConfiguration(schema: schema,
                                               url: directory.appendingPathComponent("Epilogue.sqlite"))
        let container = try ModelContainer(for: schema, migrationPlan: EpilogueMigrationPlan.self,
                                           configurations: [configuration])
        let feed = Feed(url: "https://feed.test/rss", name: "Feed", mode: .fidelity,
                        maxArticles: maxArticles)
        let articles = FixtureArticles(links: links, failed: failed,
                                       filtered: filtered, fetchFails: fetchFails)
        let generator = DigestGenerator(feedRepository: FixtureFeeds(feed),
                                        articleRepository: articles,
                                        epubBuilder: FixtureEPUB(),
                                        deliveryStore: DeliveryStore(container: container),
                                        filterSignature: DeliveryFilterSignature.make(minWordCount: 300),
                                        documentsDirectory: directory)
        return (generator, articles, container, directory)
    }

    private func links(_ count: Int) -> [String] {
        (1...count).map { "https://example.test/article/\($0)" }
    }

    @Test("A cap of two advances through five identities without repeating paid work")
    func testCapFairness() async throws {
        let (generator, articles, container, _) = try setup(maxArticles: 2, links: links(5))
        let results = try await (0..<4).asyncMap {
            _ in try await generator.generateDigest(triggerType: .manual)
        }
        #expect(results.map(\.outcome) == [.partial, .partial, .complete, .empty])
        #expect(results.map { $0.digest?.articleCount ?? 0 } == [2, 2, 1, 0])
        #expect(await articles.calls.count == 5)
        #expect(try ModelContext(container).fetchCount(FetchDescriptor<ArticleDelivery>()) == 5)
    }

    @Test("Capped regeneration advances attempt order without replacing first claims")
    func testRegenerationFairness() async throws {
        let source = links(5)
        let (generator, articles, container, _) = try setup(maxArticles: 2, links: source)
        let normal = try await generator.generateDigest(triggerType: .manual)
        let firstClaim = try #require(try ModelContext(container)
            .fetch(FetchDescriptor<ArticleDelivery>())
            .first(where: { $0.firstDigestId == normal.digest?.id }))
        let firstDigestId = try #require(firstClaim.firstDigestId)
        let repeatOne = try await generator.generateDigest(triggerType: .manual, mode: .regenerate)
        let repeatTwo = try await generator.generateDigest(triggerType: .manual, mode: .regenerate)
        #expect(repeatOne.outcome == .partial)
        #expect(repeatTwo.outcome == .partial)
        #expect(await articles.calls ==
                [source[0], source[1], source[2], source[3], source[4], source[0]])
        let originalClaim = try #require(try ModelContext(container)
            .fetch(FetchDescriptor<ArticleDelivery>())
            .first(where: { $0.identity == firstClaim.identity }))
        #expect(originalClaim.firstDigestId == firstDigestId)
        #expect(try ModelContext(container).fetchCount(FetchDescriptor<Digest>()) == 3)
    }

    @Test("A permanently failing early item moves behind unattempted candidates")
    func testFailedHeadDoesNotStarveLaterLinks() async throws {
        let source = links(5)
        let (generator, articles, container, _) = try setup(maxArticles: 2, links: source,
                                                              failed: [source[0]])
        let first = try await generator.generateDigest(triggerType: .manual)
        let second = try await generator.generateDigest(triggerType: .manual)
        let third = try await generator.generateDigest(triggerType: .manual)
        #expect([first.outcome, second.outcome, third.outcome] == [.partial, .partial, .partial])
        #expect(await articles.calls == [source[0], source[1], source[2], source[3], source[4], source[0]])
        let delivered = try ModelContext(container).fetch(FetchDescriptor<ArticleDelivery>())
        #expect(delivered.filter { $0.state == "delivered" }.count == 4)
        #expect(delivered.filter { $0.state == "retryable" }.count == 1)
    }

    @Test("Filtered-only cap overflow is deferred, then the next article is delivered")
    func testFilteredDeferred() async throws {
        let source = links(3)
        let (generator, _, container, _) = try setup(maxArticles: 2, links: source,
                                                      filtered: Set(source.prefix(2)))
        let first = try await generator.generateDigest(triggerType: .manual)
        #expect(first.outcome == .deferred)
        #expect(first.digest == nil)
        #expect(first.diagnostics.filteredCount == 2)
        #expect(first.diagnostics.deferredCount == 1)
        let second = try await generator.generateDigest(triggerType: .manual)
        #expect(second.outcome == .complete)
        #expect(second.digest?.articleCount == 1)
        let rows = try ModelContext(container).fetch(FetchDescriptor<ArticleDelivery>())
        #expect(rows.filter { $0.state == "excluded" }.count == 2)
        #expect(rows.filter { $0.state == "delivered" }.count == 1)
    }

    @Test("Fetch failure, valid empty page and cancellation retain distinct diagnostics")
    func testFailedEmptyCancelled() async throws {
        let (failedGenerator, _, failedStore, _) = try setup(maxArticles: 0, links: [], fetchFails: true)
        let failed = try await failedGenerator.generateDigest(triggerType: .manual)
        #expect(failed.outcome == .failed)
        #expect(failed.digest == nil)
        #expect(failed.diagnostics.feeds.first?.feedError == "fetch_failed")
        #expect(try ModelContext(failedStore).fetch(FetchDescriptor<GenerationRun>()).first?.outcome == "failed")

        let (emptyGenerator, _, _, _) = try setup(maxArticles: 0, links: [])
        let empty = try await emptyGenerator.generateDigest(triggerType: .manual)
        #expect(empty.outcome == .empty)

        let source = links(1)
        let (cancelledGenerator, _, cancelledStore, _) = try setup(maxArticles: 0, links: source,
                                                                   failed: [source[0] + "#cancel"])
        await #expect(throws: CancellationError.self) {
            try await cancelledGenerator.generateDigest(triggerType: .manual)
        }
        let context = ModelContext(cancelledStore)
        #expect(try context.fetchCount(FetchDescriptor<Digest>()) == 0)
        #expect(try context.fetch(FetchDescriptor<ArticleDelivery>()).first?.state == "retryable")
        #expect(try context.fetch(FetchDescriptor<GenerationRun>()).first?.outcome == "cancelled")
    }

    @Test("Duplicate normalized links and missing dates produce one candidate")
    func testIdentityDedupWithoutDates() async throws {
        let links = ["HTTPS://EXAMPLE.COM:443/Article#top", "https://example.com/Article"]
        let (generator, articles, container, _) = try setup(maxArticles: 0, links: links)
        let result = try await generator.generateDigest(triggerType: .manual)
        #expect(result.outcome == .complete)
        #expect(result.diagnostics.feeds.first?.candidateCount == 1)
        #expect(await articles.calls.count == 1)
        #expect(try ModelContext(container).fetchCount(FetchDescriptor<ArticleDelivery>()) == 1)
    }

    @Test("A failed feed does not erase a usable sibling")
    func testMixedFeedOutcome() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("delivery-mixed-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
        let configuration = ModelConfiguration(schema: schema,
                                               url: directory.appendingPathComponent("Epilogue.sqlite"))
        let container = try ModelContainer(for: schema, migrationPlan: EpilogueMigrationPlan.self,
                                           configurations: [configuration])
        let bad = Feed(url: "https://feed.test/bad", name: "Bad", mode: .fidelity)
        let good = Feed(url: "https://feed.test/good", name: "Good", mode: .fidelity)
        let source = FixtureArticles(links: ["https://example.test/article"], failed: [],
                                     filtered: [], fetchFails: false,
                                     failedFeedURLs: [bad.url])
        let generator = DigestGenerator(feedRepository: FixtureFeeds([bad, good]),
                                        articleRepository: source, epubBuilder: FixtureEPUB(),
                                        deliveryStore: DeliveryStore(container: container),
                                        filterSignature: "signature", documentsDirectory: directory)
        let result = try await generator.generateDigest(triggerType: .manual)
        #expect(result.outcome == .partial)
        #expect(result.digest?.articleCount == 1)
        #expect(result.diagnostics.failedCount == 1)
        #expect(result.diagnostics.feeds.first?.feedError == "fetch_failed")
        #expect(try ModelContext(container).fetchCount(FetchDescriptor<ArticleDelivery>()) == 1)
    }

    @Test("Post-commit failure keeps the completed run and its unique EPUB")
    func testPostCommitFailureDoesNotDemote() async throws {
        let (generator, _, container, _) = try setup(maxArticles: 0, links: links(1))
        generator.failAfterCommitForTesting = true
        let result = try await generator.generateDigest(triggerType: .manual)
        let digest = try #require(result.digest)
        #expect(result.outcome == .complete)
        #expect(FileManager.default.fileExists(atPath: digest.epubFilePath))
        let reopened = ModelContext(container)
        #expect(try reopened.fetchCount(FetchDescriptor<Digest>()) == 1)
        #expect(try reopened.fetch(FetchDescriptor<GenerationRun>()).first?.outcome == "complete")
        #expect(try reopened.fetch(FetchDescriptor<ArticleDelivery>()).first?.state == "delivered")
    }
}

private struct FixtureFeeds: FeedRepositoryProtocol, @unchecked Sendable {
    let feeds: [Feed]
    init(_ feed: Feed) { self.feeds = [feed] }
    init(_ feeds: [Feed]) { self.feeds = feeds }
    func getAllFeeds() async throws -> [Feed] { feeds }
    func getEnabledFeeds() async throws -> [Feed] { feeds }
    func getFeed(url: String) async throws -> Feed? { feeds.first { $0.url == url } }
    func addFeed(_ feed: Feed) async throws {}
    func updateFeed(_ feed: Feed) async throws {}
    func deleteFeed(url: String) async throws {}
    func updateLastFetched(url: String, timestamp: Int64) async throws {}
    func feedExists(url: String) async throws -> Bool { feeds.contains { $0.url == url } }
    func upsertAll(_ feeds: [Feed]) async throws {}
    func deleteByURLs(_ urls: [String]) async throws {}
    func clearAllLocallyModified() async throws {}
    func getLocallyModifiedFeeds() async throws -> [Feed] { [] }
    func markAsLocallyModified(url: String) async throws {}
}

private actor FixtureArticles: ArticleRepositoryProtocol {
    let links: [String]
    let failed: Set<String>
    let filtered: Set<String>
    let fetchFails: Bool
    let failedFeedURLs: Set<String>
    var calls: [String] = []

    init(links: [String], failed: Set<String>, filtered: Set<String>, fetchFails: Bool,
         failedFeedURLs: Set<String> = []) {
        self.links = links
        self.failed = failed
        self.filtered = filtered
        self.fetchFails = fetchFails
        self.failedFeedURLs = failedFeedURLs
    }

    func fetchAndProcessArticles() async throws -> [ProcessedArticle] { [] }
    func fetchAndProcessArticles(from feed: Feed) async throws -> [ProcessedArticle] { [] }
    func fetchFeedArticles(feedUrl: String) async throws -> [RawArticle] {
        if fetchFails || failedFeedURLs.contains(feedUrl) { throw FixtureError.failure }
        return links.map { RawArticle(title: "Article", link: $0,
                                      feedUrl: feedUrl, feedName: "Feed") }
    }
    func processArticle(_ article: RawArticle, mode: ProcessingMode) async throws -> ProcessedArticle {
        calls.append(article.link)
        if failed.contains(article.link + "#cancel") { throw CancellationError() }
        if failed.contains(article.link) { throw FixtureError.failure }
        if filtered.contains(article.link) { throw ArticleProcessingError.contentTooShort }
        return ProcessedArticle(title: "Article", content: "<p>Body</p>",
                                originalUrl: article.link, feedUrl: article.feedUrl,
                                feedName: article.feedName, isSummary: false)
    }
    func extractFullContent(url: String) async throws -> String { "Body" }
    func validateFeedUrl(_ url: String) async throws -> Bool { true }
}

private struct FixtureEPUB: EPUBBuilderProtocol {
    func generateEPUB(articles: [ProcessedArticle], outputPath: String, date: Date) throws -> URL {
        let url = URL(fileURLWithPath: outputPath)
        try Data("EPUB".utf8).write(to: url)
        return url
    }
}

private enum FixtureError: Error { case failure }

private extension Range where Element == Int {
    func asyncMap<T>(_ transform: (Int) async throws -> T) async rethrows -> [T] {
        var result: [T] = []
        for value in self { result.append(try await transform(value)) }
        return result
    }
}
