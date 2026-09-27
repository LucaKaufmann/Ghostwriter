import Foundation
import SwiftData
import Domain

// Frozen copy of the three unversioned persisted classes from the Domain module
// at ad7fd3e. Keep unchanged when the shipping models move to versioned schemas.
// The migration probe verifies this exact captured V1 can identify and migrate
// a disk store written with the original Domain classes.
enum CapturedSwiftDataV1: VersionedSchema {
    static var versionIdentifier = Schema.Version(1, 0, 0)
    static var models: [any PersistentModel.Type] {
        [Feed.self, Digest.self, DigestArticle.self]
    }

    @Model
    final class Feed {
        /// The feed URL (primary identifier)
        @Attribute(.unique) var url: String

        /// User-provided name for the feed
        var name: String

        /// Processing mode for articles from this feed
        var mode: ProcessingMode

        /// Timestamp of last successful fetch (milliseconds since epoch)
        var lastFetched: Int64

        /// Maximum number of articles to fetch per digest (0 = unlimited)
        var maxArticles: Int

        /// Whether this feed is currently enabled
        var isEnabled: Bool

        /// Timestamp when this feed was added
        var createdAt: Date

        // MARK: - Ghostwriter Sync Fields

        /// Timestamp of when the server last updated this feed (for sync)
        var serverUpdatedAt: Date?

        /// Whether this feed has been modified locally and needs to be synced
        var locallyModified: Bool

        init(
            url: String,
            name: String,
            mode: ProcessingMode,
            lastFetched: Int64 = 0,
            maxArticles: Int = 0,
            isEnabled: Bool = true,
            createdAt: Date = Date(),
            serverUpdatedAt: Date? = nil,
            locallyModified: Bool = false
        ) {
            self.url = url
            self.name = name
            self.mode = mode
            self.lastFetched = lastFetched
            self.maxArticles = maxArticles
            self.isEnabled = isEnabled
            self.createdAt = createdAt
            self.serverUpdatedAt = serverUpdatedAt
            self.locallyModified = locallyModified
        }
    }

    @Model
    final class Digest {
        /// Unique identifier for the digest
        @Attribute(.unique) var id: UUID

        /// Timestamp when the digest was generated
        var generatedAt: Date

        /// File path to the generated EPUB file
        var epubFilePath: String

        /// Number of articles included in the digest
        var articleCount: Int

        /// Number of briefing articles in the digest
        var briefingCount: Int

        /// Number of full-content articles in the digest
        var deepDiveCount: Int

        /// How the digest was triggered
        var triggerType: TriggerType

        /// Total size of the EPUB file in bytes
        var fileSizeBytes: Int64

        /// Whether the digest generation completed successfully
        var isComplete: Bool

        /// Error message if generation failed
        var errorMessage: String?

        // MARK: - Ghostwriter Sync Fields

        /// Remote ID from Ghostwriter server (nil if locally generated)
        var remoteId: String?

        /// Period of the digest (morning, noon, evening, manual)
        var period: String?

        /// Relationship to articles in this digest
        @Relationship(deleteRule: .cascade, inverse: \DigestArticle.digest)
        var articles: [DigestArticle]

        init(
            id: UUID = UUID(),
            generatedAt: Date = Date(),
            epubFilePath: String,
            articleCount: Int = 0,
            briefingCount: Int = 0,
            deepDiveCount: Int = 0,
            triggerType: TriggerType,
            fileSizeBytes: Int64 = 0,
            isComplete: Bool = false,
            errorMessage: String? = nil,
            remoteId: String? = nil,
            period: String? = nil,
            articles: [DigestArticle] = []
        ) {
            self.id = id
            self.generatedAt = generatedAt
            self.epubFilePath = epubFilePath
            self.articleCount = articleCount
            self.briefingCount = briefingCount
            self.deepDiveCount = deepDiveCount
            self.triggerType = triggerType
            self.fileSizeBytes = fileSizeBytes
            self.isComplete = isComplete
            self.errorMessage = errorMessage
            self.remoteId = remoteId
            self.period = period
            self.articles = articles
        }
    }

    @Model
    final class DigestArticle {
        /// Unique identifier for the digest article
        @Attribute(.unique) var id: UUID

        /// The parent digest this article belongs to
        var digest: Digest?

        /// Article title
        var title: String

        /// Article author (may be empty)
        var author: String

        /// Processed content (HTML or Markdown depending on processing mode)
        var content: String

        /// Original article URL
        var originalUrl: String

        /// Source feed URL
        var feedUrl: String

        /// Source feed name
        var feedName: String

        /// Type of content (briefing or deep dive)
        var contentType: ContentType

        /// Timestamp when the article was published (if available)
        var publishedAt: Date?

        /// Order/position in the digest (for sorting)
        var orderIndex: Int

        /// Word count of the processed content
        var wordCount: Int

        init(
            id: UUID = UUID(),
            digest: Digest? = nil,
            title: String,
            author: String = "",
            content: String,
            originalUrl: String,
            feedUrl: String,
            feedName: String,
            contentType: ContentType,
            publishedAt: Date? = nil,
            orderIndex: Int = 0,
            wordCount: Int = 0
        ) {
            self.id = id
            self.digest = digest
            self.title = title
            self.author = author
            self.content = content
            self.originalUrl = originalUrl
            self.feedUrl = feedUrl
            self.feedName = feedName
            self.contentType = contentType
            self.publishedAt = publishedAt
            self.orderIndex = orderIndex
            self.wordCount = wordCount
        }
    }
}
