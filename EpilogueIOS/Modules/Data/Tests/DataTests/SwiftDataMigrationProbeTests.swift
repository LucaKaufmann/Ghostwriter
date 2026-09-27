import Foundation
import SwiftData
import Testing
import Domain

// The old store is written with the shipping Domain classes below. Its V1
// migration schema is a separate frozen copy in CapturedSwiftDataV1.swift.
private enum ProbeV2: VersionedSchema {
    static var versionIdentifier = Schema.Version(2, 0, 0)
    static var models: [any PersistentModel.Type] {
        [Feed.self, Digest.self, DigestArticle.self]
    }

    @Model
    final class Feed {
        @Attribute(.unique) var url: String
        var name: String
        var mode: ProcessingMode
        var lastFetched: Int64
        var maxArticles: Int
        var isEnabled: Bool
        var createdAt: Date
        var serverUpdatedAt: Date?
        var locallyModified: Bool

        // Additive fields reserved for a durable four-field local proposal.
        var proposalName: String?
        var proposalMode: ProcessingMode?
        var proposalMaxArticles: Int?
        var proposalIsEnabled: Bool?

        init(url: String, name: String, mode: ProcessingMode,
             lastFetched: Int64 = 0, maxArticles: Int = 0,
             isEnabled: Bool = true, createdAt: Date = Date(),
             serverUpdatedAt: Date? = nil, locallyModified: Bool = false,
             proposalName: String? = nil, proposalMode: ProcessingMode? = nil,
             proposalMaxArticles: Int? = nil, proposalIsEnabled: Bool? = nil) {
            self.url = url
            self.name = name
            self.mode = mode
            self.lastFetched = lastFetched
            self.maxArticles = maxArticles
            self.isEnabled = isEnabled
            self.createdAt = createdAt
            self.serverUpdatedAt = serverUpdatedAt
            self.locallyModified = locallyModified
            self.proposalName = proposalName
            self.proposalMode = proposalMode
            self.proposalMaxArticles = proposalMaxArticles
            self.proposalIsEnabled = proposalIsEnabled
        }
    }
}

private enum ProbePlan: SchemaMigrationPlan {
    static var schemas: [any VersionedSchema.Type] { [CapturedSwiftDataV1.self, ProbeV2.self] }
    static var stages: [MigrationStage] {
        [.custom(fromVersion: CapturedSwiftDataV1.self, toVersion: ProbeV2.self,
                 willMigrate: nil, didMigrate: { context in
            let feeds = try context.fetch(FetchDescriptor<ProbeV2.Feed>())
            for feed in feeds {
                feed.proposalName = feed.name
                feed.proposalMode = feed.mode
                feed.proposalMaxArticles = feed.maxArticles
                feed.proposalIsEnabled = feed.isEnabled
            }
            try context.save()
        })]
    }
}

@Suite("SwiftData unversioned store migration probe")
@MainActor
struct SwiftDataMigrationProbeTests {
    @Test("Frozen V1 independently writes a legacy unversioned store that V2 can migrate")
    func testCapturedLegacyStoreUpgrade() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("epilogue-captured-v1-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent("Epilogue.sqlite")
        defer { try? FileManager.default.removeItem(at: directory) }
        let digestID = UUID()
        let articleID = UUID()

        do {
            // No Domain @Model participates in this independent legacy fixture.
            let schema = Schema([CapturedSwiftDataV1.Feed.self,
                                 CapturedSwiftDataV1.Digest.self,
                                 CapturedSwiftDataV1.DigestArticle.self])
            let config = ModelConfiguration(schema: schema, url: url)
            let container = try ModelContainer(for: schema, configurations: [config])
            let context = ModelContext(container)
            context.insert(CapturedSwiftDataV1.Feed(
                url: "https://example.test/legacy", name: "Legacy proposal",
                mode: .fidelity, lastFetched: 73, maxArticles: 0,
                isEnabled: false, locallyModified: false))
            let digest = CapturedSwiftDataV1.Digest(
                id: digestID, epubFilePath: "/tmp/captured-v1.epub",
                articleCount: 1, briefingCount: 1, triggerType: .manual,
                isComplete: true)
            let article = CapturedSwiftDataV1.DigestArticle(
                id: articleID, digest: digest, title: "Legacy article",
                content: "Body", originalUrl: "https://example.test/article",
                feedUrl: "https://example.test/legacy", feedName: "Legacy proposal",
                contentType: .briefing)
            context.insert(digest)
            context.insert(article)
            try context.save()
        }
        #expect(FileManager.default.fileExists(atPath: url.path))

        func verify() throws {
            let schema = Schema(versionedSchema: ProbeV2.self)
            let config = ModelConfiguration(schema: schema, url: url)
            let container = try ModelContainer(for: schema,
                                               migrationPlan: ProbePlan.self,
                                               configurations: [config])
            let context = ModelContext(container)
            let feed = try #require(context.fetch(FetchDescriptor<ProbeV2.Feed>()).first)
            #expect(feed.url == "https://example.test/legacy")
            #expect(feed.name == "Legacy proposal")
            #expect(feed.mode == .fidelity)
            #expect(feed.maxArticles == 0)
            #expect(feed.isEnabled == false)
            #expect(feed.locallyModified == false)
            #expect(feed.proposalName == "Legacy proposal")
            #expect(feed.proposalMode == .fidelity)
            #expect(feed.proposalMaxArticles == 0)
            #expect(feed.proposalIsEnabled == false)
            let digest = try #require(context.fetch(FetchDescriptor<Digest>()).first)
            #expect(digest.id == digestID)
            #expect(digest.articles.first?.id == articleID)
            #expect(digest.articles.first?.digest?.id == digestID)
        }
        try verify()
        try verify()
    }

    @Test("Shipping unversioned store migrates through independent captured V1 and reopens V2")
    func testShippingStoreUpgrade() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("epilogue-swiftdata-probe-\(UUID().uuidString)", isDirectory: true)
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
            // This is the same unversioned Schema + ModelContainer form as PersistenceController.
            let schema = Schema([Feed.self, Digest.self, DigestArticle.self])
            let config = ModelConfiguration(schema: schema, url: url)
            let container = try ModelContainer(for: schema, configurations: [config])
            let context = ModelContext(container)
            for (url, name, mode, maxArticles, isEnabled, locallyModified) in feedValues {
                context.insert(Feed(url: url, name: name, mode: mode,
                                    lastFetched: 42, maxArticles: maxArticles,
                                    isEnabled: isEnabled,
                                    createdAt: Date(timeIntervalSince1970: 1_700_000_000),
                                    serverUpdatedAt: Date(timeIntervalSince1970: 1_700_000_100),
                                    locallyModified: locallyModified))
            }
            let digest = Digest(id: digestID,
                                generatedAt: Date(timeIntervalSince1970: 1_700_000_200),
                                epubFilePath: "/tmp/fixture.epub", articleCount: 1,
                                briefingCount: 1, deepDiveCount: 0, triggerType: .manual,
                                fileSizeBytes: 123, isComplete: true,
                                remoteId: "remote-fixture", period: "morning")
            let article = DigestArticle(id: articleID, digest: digest,
                                        title: "Article", author: "Author", content: "Body",
                                        originalUrl: "https://example.test/article",
                                        feedUrl: "https://example.test/dirty", feedName: "Edited",
                                        contentType: .briefing, orderIndex: 0, wordCount: 1)
            context.insert(digest)
            context.insert(article)
            try context.save()
            #expect(try context.fetchCount(FetchDescriptor<Feed>()) == 3)
        }
        #expect(FileManager.default.fileExists(atPath: url.path))

        func verify(_ container: ModelContainer) throws {
            let context = ModelContext(container)
            let feeds = try context.fetch(FetchDescriptor<ProbeV2.Feed>())
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
                #expect(feed.proposalName == name)
                #expect(feed.proposalMode == mode)
                #expect(feed.proposalMaxArticles == maxArticles)
                #expect(feed.proposalIsEnabled == isEnabled)
            }
            let digests = try context.fetch(FetchDescriptor<Digest>())
            let digest = try #require(digests.first { $0.id == digestID })
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
            #expect(digest.articles.count == 1)
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
            #expect(article.publishedAt == nil)
            #expect(article.orderIndex == 0)
            #expect(article.wordCount == 1)
        }

        do {
            let schema = Schema(versionedSchema: ProbeV2.self)
            let config = ModelConfiguration(schema: schema, url: url)
            let container = try ModelContainer(for: schema,
                                               migrationPlan: ProbePlan.self,
                                               configurations: [config])
            try verify(container)
        }
        do {
            let schema = Schema(versionedSchema: ProbeV2.self)
            let config = ModelConfiguration(schema: schema, url: url)
            let container = try ModelContainer(for: schema,
                                               migrationPlan: ProbePlan.self,
                                               configurations: [config])
            try verify(container)
        }
    }
}
