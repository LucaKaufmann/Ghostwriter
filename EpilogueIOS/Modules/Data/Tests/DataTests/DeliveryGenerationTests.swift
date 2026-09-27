import Foundation
import SwiftData
import Testing
import Domain
@testable import Data

@Suite("Incremental local generation")
@MainActor
struct DeliveryGenerationTests {
    private func diskModel() throws -> (ModelContainer, URL) {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("delivery-generator-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
        let configuration = ModelConfiguration(schema: schema,
                                               url: directory.appendingPathComponent("Epilogue.sqlite"))
        return (try ModelContainer(for: schema, migrationPlan: EpilogueMigrationPlan.self,
                                   configurations: [configuration]), directory)
    }

    private func setup(maxArticles: Int, links: [String],
                       failed: Set<String> = [], filtered: Set<String> = [],
                       fetchFails: Bool = false) throws -> (DigestGenerator, FixtureArticles, ModelContainer, URL) {
        let (container, directory) = try diskModel()
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

    private func seedFutureHistory(container: ModelContainer, directory: URL,
                                   count: Int = 30) throws -> [String] {
        let context = ModelContext(container)
        context.autosaveEnabled = false
        var paths: [String] = []
        for index in 0..<count {
            let path = directory.appendingPathComponent("old-\(index).epub").path
            try Data("OLD".utf8).write(to: URL(fileURLWithPath: path))
            context.insert(Digest(
                generatedAt: Date().addingTimeInterval(Double(index + 1) * 86_400),
                epubFilePath: path, articleCount: 1, triggerType: .manual,
                isComplete: true))
            paths.append(path)
        }
        try context.save()
        return paths
    }

    private func oneArticleGenerator(container: ModelContainer, directory: URL,
                                     store: DeliveryStore) -> DigestGenerator {
        DigestGenerator(
            feedRepository: FixtureFeeds(Feed(url: "https://feed.test/rss", name: "Feed",
                                            mode: .fidelity)),
            articleRepository: FixtureArticles(links: ["https://example.test/article"],
                                               failed: [], filtered: [], fetchFails: false),
            epubBuilder: FixtureEPUB(), deliveryStore: store,
            filterSignature: DeliveryFilterSignature.make(minWordCount: 300),
            documentsDirectory: directory)
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

    @Test("Missing EPUB retains deliver-once claim; automatic retry is empty until explicit regeneration")
    func testMissingArtifactDoesNotAutomaticallyRepeatDeliveredArticle() async throws {
        let link = "https://example.test/article"
        let (generator, articles, container, _) = try setup(maxArticles: 0, links: [link])
        let start = Date(timeIntervalSince1970: 1_800_000_000)
        let first = try await generator.generateDigest(triggerType: .scheduled,
                                                       period: "MORNING", now: start)
        let firstDigest = try #require(first.digest)
        #expect(first.outcome == .complete)
        let firstID = firstDigest.id
        let firstPath = firstDigest.epubFilePath
        try FileManager.default.removeItem(atPath: firstPath)
        let context = ModelContext(container)
        let original = try #require(context.fetch(FetchDescriptor<GenerationRun>()).first)
        original.outcome = "running"
        original.finishedAt = nil
        try context.save()

        let store = DeliveryStore(container: container)
        try store.reconcileInterruptedLocalRuns(now: start.addingTimeInterval(30))
        let end = start.addingTimeInterval(86_400)
        #expect(try store.mayStartScheduled(period: "MORNING", occurrenceStart: start,
                                            occurrenceEnd: end, legacyCovered: false))
        let retry = try #require(try await generator.generateScheduledIfEligible(
            period: "MORNING", occurrenceStart: start, occurrenceEnd: end,
            now: start.addingTimeInterval(60)) { false })
        #expect(retry.outcome == .empty)
        #expect(retry.digest == nil)
        #expect(await articles.calls == [link])
        #expect(try !store.mayStartScheduled(period: "MORNING", occurrenceStart: start,
                                             occurrenceEnd: end, legacyCovered: false))
        let afterRetry = ModelContext(container)
        let claim = try #require(afterRetry.fetch(FetchDescriptor<ArticleDelivery>()).first)
        let missingDigest = try #require(afterRetry.fetch(FetchDescriptor<Digest>())
            .first(where: { $0.id == firstID }))
        #expect(claim.state == "delivered")
        #expect(claim.firstDigestId == firstID)
        #expect(!missingDigest.isComplete)
        #expect(!FileManager.default.fileExists(atPath: firstPath))

        let explicit = try await generator.generateDigest(triggerType: .manual,
                                                           mode: .regenerate,
                                                           now: start.addingTimeInterval(120))
        #expect(explicit.outcome == .complete)
        #expect(explicit.digest?.articleCount == 1)
        #expect(await articles.calls == [link, link])
        #expect(try ModelContext(container).fetch(FetchDescriptor<ArticleDelivery>())
            .first?.firstDigestId == firstID)
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

    @Test("Changing a feed from Fidelity to Briefing retries its earlier short-content exclusion")
    func testModeChangeReconsidersExclusion() async throws {
        let link = "https://example.test/short"
        let (fidelityGenerator, articles, container, directory) = try setup(
            maxArticles: 0, links: [link], filtered: [link])
        let first = try await fidelityGenerator.generateDigest(triggerType: .manual)
        #expect(first.outcome == .empty)
        let original = try #require(try ModelContext(container)
            .fetch(FetchDescriptor<ArticleDelivery>()).first)
        #expect(original.state == "excluded")
        let firstSignature = try #require(original.filterSignature)

        let briefing = Feed(url: "https://feed.test/rss", name: "Feed", mode: .briefing)
        let briefingGenerator = DigestGenerator(
            feedRepository: FixtureFeeds(briefing), articleRepository: articles,
            epubBuilder: FixtureEPUB(), deliveryStore: DeliveryStore(container: container),
            filterSignature: DeliveryFilterSignature.make(minWordCount: 300),
            documentsDirectory: directory)
        let second = try await briefingGenerator.generateDigest(triggerType: .manual)
        #expect(second.outcome == .complete)
        #expect(second.digest?.articleCount == 1)
        let delivered = try #require(try ModelContext(container)
            .fetch(FetchDescriptor<ArticleDelivery>()).first)
        #expect(delivered.state == "delivered")
        #expect(delivered.filterSignature == nil)
        #expect(firstSignature != DeliveryFilterSignature.forFeed(
            base: DeliveryFilterSignature.make(minWordCount: 300), mode: .briefing))
        let third = try await fidelityGenerator.generateDigest(triggerType: .manual)
        #expect(third.outcome == .empty)
        #expect(await articles.calls == [link, link])
    }

    @Test("Retention prunes older local history and files without erasing delivery claims")
    func testRetentionPreservesLedger() async throws {
        let (generator, _, container, _) = try setup(maxArticles: 1, links: links(31))
        var firstDigestId: UUID?
        var firstPath: String?
        for index in 0..<31 {
            let result = try await generator.generateDigest(triggerType: .manual)
            let digest = try #require(result.digest)
            if index == 0 {
                firstDigestId = digest.id
                firstPath = digest.epubFilePath
            }
        }
        let reopened = ModelContext(container)
        #expect(try reopened.fetchCount(FetchDescriptor<Digest>()) == 30)
        #expect(try reopened.fetchCount(FetchDescriptor<ArticleDelivery>()) == 31)
        #expect(try reopened.fetch(FetchDescriptor<Digest>()).allSatisfy {
            FileManager.default.fileExists(atPath: $0.epubFilePath)
        })
        #expect(firstPath.map { !FileManager.default.fileExists(atPath: $0) } == true)
        #expect(try reopened.fetch(FetchDescriptor<ArticleDelivery>())
            .contains { $0.firstDigestId == firstDigestId })
    }

    @Test("A clock-behind edition remains in history and usable after retention")
    func testRetentionProtectsNewEdition() async throws {
        let (container, directory) = try diskModel()
        let priorPaths = try seedFutureHistory(container: container, directory: directory)
        let generator = oneArticleGenerator(
            container: container, directory: directory,
            store: DeliveryStore(container: container))
        let result = try await generator.generateDigest(triggerType: .manual)
        let digest = try #require(result.digest)
        let reopened = ModelContext(container)
        #expect(try reopened.fetchCount(FetchDescriptor<Digest>()) == 30)
        #expect(try reopened.fetch(FetchDescriptor<Digest>()).contains { $0.id == digest.id })
        #expect(FileManager.default.fileExists(atPath: digest.epubFilePath))
        #expect(!FileManager.default.fileExists(atPath: priorPaths[0]))
        #expect(try reopened.fetch(FetchDescriptor<ArticleDelivery>()).first?.firstDigestId == digest.id)
    }

    @Test("Retention keeps a shared legacy file while another digest references it")
    func testRetentionRespectsSharedPaths() throws {
        let (container, directory) = try diskModel()
        let context = ModelContext(container)
        context.autosaveEnabled = false
        let shared = directory.appendingPathComponent("shared.epub").path
        try Data("SHARED".utf8).write(to: URL(fileURLWithPath: shared))
        var newestID: UUID?
        for index in 0..<31 {
            let path = index == 0 || index == 30 ? shared :
                directory.appendingPathComponent("old-\(index).epub").path
            if index != 0 && index != 30 {
                try Data("OLD".utf8).write(to: URL(fileURLWithPath: path))
            }
            let digest = Digest(generatedAt: Date().addingTimeInterval(Double(index) * 86_400),
                                epubFilePath: path, triggerType: .manual, isComplete: true)
            context.insert(digest)
            if index == 30 { newestID = digest.id }
        }
        try context.save()
        let store = DeliveryStore(container: container)
        try store.enforceRetentionPolicy(protectedDigestId: try #require(newestID))
        let reopened = ModelContext(container)
        #expect(try reopened.fetchCount(FetchDescriptor<Digest>()) == 30)
        #expect(FileManager.default.fileExists(atPath: shared))
        #expect(try reopened.fetch(FetchDescriptor<Digest>()).contains { $0.epubFilePath == shared })
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

    @Test("Retention failure after commit leaves completed history, claim and artifact usable")
    func testRetentionFailureDoesNotDemote() async throws {
        let (container, directory) = try diskModel()
        let priorPaths = try seedFutureHistory(container: container, directory: directory)
        let store = DeliveryStore(container: container)
        store.failNextRetentionForTesting = true
        let generator = oneArticleGenerator(container: container, directory: directory,
                                            store: store)
        let result = try await generator.generateDigest(triggerType: .manual)
        let digest = try #require(result.digest)
        #expect(result.outcome == .complete)
        #expect(FileManager.default.fileExists(atPath: digest.epubFilePath))
        let reopened = ModelContext(container)
        #expect(try reopened.fetchCount(FetchDescriptor<Digest>()) == 31)
        #expect(priorPaths.allSatisfy { FileManager.default.fileExists(atPath: $0) })
        #expect(try reopened.fetch(FetchDescriptor<Digest>()).contains { $0.id == digest.id })
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
        if filtered.contains(article.link) && mode == .fidelity {
            throw ArticleProcessingError.contentTooShort
        }
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
