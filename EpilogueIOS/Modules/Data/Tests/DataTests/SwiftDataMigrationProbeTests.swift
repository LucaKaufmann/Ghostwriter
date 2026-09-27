import Foundation
import SwiftData
import Testing
import Domain
@testable import Data

@Suite("SwiftData delivery migration")
@MainActor
struct SwiftDataMigrationProbeTests {
    @Test("Independent captured unversioned store migrates through V1, V2 and V3 and reopens")
    func testLegacyStoreUpgrade() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("epilogue-legacy-v1-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent("Epilogue.sqlite")
        defer { try? FileManager.default.removeItem(at: directory) }

        let feedValues: [(String, String, ProcessingMode, Int, Bool, Bool)] = [
            ("https://example.test/dirty", "Edited", .briefing, 0, false, true),
            ("https://example.test/clean", "Clean proposal", .fidelity, 7, true, false),
            ("synthetic://local", "Synthetic", .briefing, 3, true, false)
        ]
        let digestID = UUID()
        let articleID = UUID()
        do {
            // This unversioned model copy was proven to match the shipping
            // Domain model in the two pre-implementation simulator tests.
            let schema = Schema([CapturedSwiftDataV1.Feed.self,
                                 CapturedSwiftDataV1.Digest.self,
                                 CapturedSwiftDataV1.DigestArticle.self])
            let config = ModelConfiguration(schema: schema, url: url)
            let container = try ModelContainer(for: schema, configurations: [config])
            let context = ModelContext(container)
            for (url, name, mode, maxArticles, isEnabled, locallyModified) in feedValues {
                context.insert(CapturedSwiftDataV1.Feed(
                    url: url, name: name, mode: mode, lastFetched: 42,
                    maxArticles: maxArticles, isEnabled: isEnabled,
                    createdAt: Date(timeIntervalSince1970: 1_700_000_000),
                    serverUpdatedAt: Date(timeIntervalSince1970: 1_700_000_100),
                    locallyModified: locallyModified))
            }
            let digest = CapturedSwiftDataV1.Digest(
                id: digestID,
                generatedAt: Date(timeIntervalSince1970: 1_700_000_200),
                epubFilePath: "/tmp/fixture.epub", articleCount: 1,
                briefingCount: 1, deepDiveCount: 0, triggerType: .manual,
                fileSizeBytes: 123, isComplete: true,
                remoteId: "remote-fixture", period: "morning")
            let article = CapturedSwiftDataV1.DigestArticle(
                id: articleID, digest: digest,
                title: "Article", author: "Author", content: "Body",
                originalUrl: "https://example.test/article",
                feedUrl: "https://example.test/dirty", feedName: "Edited",
                contentType: .briefing, orderIndex: 0, wordCount: 1)
            context.insert(digest)
            context.insert(article)
            try context.save()
            #expect(try context.fetchCount(FetchDescriptor<CapturedSwiftDataV1.Feed>()) == 3)
        }
        #expect(FileManager.default.fileExists(atPath: url.path))

        func verify(_ container: ModelContainer) throws {
            let context = ModelContext(container)
            let feeds = try context.fetch(FetchDescriptor<Feed>())
            #expect(feeds.count == 3)
            for (url, name, mode, maxArticles, isEnabled, locallyModified) in feedValues {
                let feed = try #require(feeds.first { $0.url == url })
                #expect(feed.name == name)
                #expect(feed.mode == mode)
                #expect(feed.maxArticles == maxArticles)
                #expect(feed.isEnabled == isEnabled)
                #expect(feed.locallyModified == locallyModified)
                #expect(feed.lastFetched == 42)
                #expect(feed.createdAt == Date(timeIntervalSince1970: 1_700_000_000))
                #expect(feed.serverUpdatedAt == Date(timeIntervalSince1970: 1_700_000_100))
                #expect(feed.serverVersion == nil)
                #expect(feed.mutationRevision == 0)
            }
            let mutations = try context.fetch(FetchDescriptor<FeedMutation>())
            #expect(mutations.count == 2)
            for (url, name, mode, maxArticles, isEnabled, _) in feedValues
            where !url.hasPrefix("synthetic://") {
                let mutation = try #require(mutations.first { $0.url == url })
                #expect(mutation.status == "needs_reconciliation")
                #expect(mutation.origin == "legacy")
                #expect(mutation.title == name)
                #expect(mutation.mode == (mode == .briefing ? "summarize" : "raw"))
                #expect(mutation.maxArticles == maxArticles)
                #expect(mutation.isActive == isEnabled)
                #expect(mutation.sent == false)
            }
            let state = try #require(context.fetch(FetchDescriptor<FeedSyncState>()).first)
            #expect(state.key == "main")
            #expect(state.firstReconciliationComplete == false)
            #expect(state.nextSequence == 3)
            let digest = try #require(context.fetch(FetchDescriptor<Digest>()).first)
            #expect(digest.id == digestID)
            #expect(digest.generatedAt == Date(timeIntervalSince1970: 1_700_000_200))
            #expect(digest.epubFilePath == "/tmp/fixture.epub")
            #expect(digest.articleCount == 1)
            #expect(digest.briefingCount == 1)
            #expect(digest.deepDiveCount == 0)
            #expect(digest.triggerType == .manual)
            #expect(digest.fileSizeBytes == 123)
            #expect(digest.isComplete)
            #expect(digest.errorMessage == nil)
            #expect(digest.remoteId == "remote-fixture")
            #expect(digest.period == "morning")
            let article = try #require(digest.articles.first)
            #expect(article.id == articleID)
            #expect(article.digest?.id == digestID)
            #expect(article.title == "Article")
            #expect(article.author == "Author")
            #expect(article.content == "Body")
            #expect(article.originalUrl == "https://example.test/article")
            #expect(article.feedUrl == "https://example.test/dirty")
            #expect(article.feedName == "Edited")
            #expect(article.contentType == .briefing)
            #expect(article.orderIndex == 0)
            #expect(article.wordCount == 1)
        }

        for _ in 0..<2 {
            let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
            let config = ModelConfiguration(schema: schema, url: url)
            let container = try ModelContainer(for: schema,
                                               migrationPlan: EpilogueMigrationPlan.self,
                                               configurations: [config])
            try verify(container)
            #expect(try ModelContext(container).fetch(FetchDescriptor<ArticleDelivery>()).isEmpty)
        }
    }

    @Test("Frozen V2 store backfills only provable completed local articles")
    func testV2Backfill() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("epilogue-delivery-v2-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent("Epilogue.sqlite")
        defer { try? FileManager.default.removeItem(at: directory) }
        let localID = UUID()
        do {
            let schema = Schema(versionedSchema: EpilogueSchemaV2.self)
            let config = ModelConfiguration(schema: schema, url: url)
            let container = try ModelContainer(for: schema, configurations: [config])
            let context = ModelContext(container)
            let local = EpilogueSchemaV2.Digest(id: localID, epubFilePath: "/tmp/local.epub",
                                                articleCount: 2, triggerType: .manual,
                                                isComplete: true)
            let valid = EpilogueSchemaV2.DigestArticle(
                digest: local, title: "Valid", content: "Body",
                originalUrl: "HTTPS://Example.com:443/Article?q=1#section",
                feedUrl: "https://feed.test/rss", feedName: "Feed", contentType: .deepDive)
            let invalid = EpilogueSchemaV2.DigestArticle(
                digest: local, title: "Missing link", content: "Body", originalUrl: "",
                feedUrl: "https://feed.test/rss", feedName: "Feed", contentType: .deepDive)
            let remote = EpilogueSchemaV2.Digest(epubFilePath: "/tmp/remote.epub",
                                                 articleCount: 1, triggerType: .ghostwriter,
                                                 isComplete: true, remoteId: "server-id")
            let remoteArticle = EpilogueSchemaV2.DigestArticle(
                digest: remote, title: "Remote", content: "Body",
                originalUrl: "https://example.test/remote",
                feedUrl: "https://feed.test/rss", feedName: "Feed", contentType: .deepDive)
            let failed = EpilogueSchemaV2.Digest(epubFilePath: "/tmp/failed.epub",
                                                 articleCount: 1, triggerType: .manual,
                                                 isComplete: false)
            let failedArticle = EpilogueSchemaV2.DigestArticle(
                digest: failed, title: "Failed", content: "Body",
                originalUrl: "https://example.test/failed",
                feedUrl: "https://feed.test/rss", feedName: "Feed", contentType: .deepDive)
            for digest in [local, remote, failed] { context.insert(digest) }
            for article in [valid, invalid, remoteArticle, failedArticle] { context.insert(article) }
            try context.save()
        }
        for _ in 0..<2 {
            let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
            let config = ModelConfiguration(schema: schema, url: url)
            let container = try ModelContainer(for: schema,
                                               migrationPlan: EpilogueMigrationPlan.self,
                                               configurations: [config])
            let context = ModelContext(container)
            let digests = try context.fetch(FetchDescriptor<Digest>())
            #expect(digests.count == 3)
            let delivered = try context.fetch(FetchDescriptor<ArticleDelivery>())
            #expect(delivered.count == 1)
            let claim = try #require(delivered.first)
            #expect(claim.feedUrl == "https://feed.test/rss")
            #expect(claim.state == "delivered")
            #expect(claim.firstDigestId == localID)
        }
    }
}
