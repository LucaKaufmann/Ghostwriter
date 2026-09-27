import Foundation
import SwiftData

// Frozen SwiftData V2 shape from accepted iOS feed sync. Do not edit it when
// changing the live V3 models: captured V1 and existing V2 stores need it.
public enum EpilogueSchemaV2: VersionedSchema {
    public static var versionIdentifier = Schema.Version(2, 0, 0)
    public static var models: [any PersistentModel.Type] {
        [Feed.self, Digest.self, DigestArticle.self, FeedMutation.self, FeedSyncState.self]
    }

    @Model
    public final class Feed {
        /// The feed URL (primary identifier)
        @Attribute(.unique) public var url: String

        /// User-provided name for the feed
        public var name: String

        /// Processing mode for articles from this feed
        public var mode: ProcessingMode

        /// Timestamp of last successful fetch (milliseconds since epoch)
        public var lastFetched: Int64

        /// Maximum number of articles to fetch per digest (0 = unlimited)
        public var maxArticles: Int

        /// Whether this feed is currently enabled
        public var isEnabled: Bool

        /// Timestamp when this feed was added
        public var createdAt: Date

        // MARK: - Ghostwriter Sync Fields

        /// Timestamp of when the server last updated this feed (for sync)
        public var serverUpdatedAt: Date?

        /// Whether this feed has been modified locally and needs to be synced
        public var locallyModified: Bool

        /// Server-owned identity and version; nil until a complete v2 reconciliation.
        public var serverId: String?
        public var serverVersion: Int64?

        /// Incremented in the same save that creates each local intent.
        public var mutationRevision: Int64?

        /// A pending local delete keeps its row and server identity durable.
        public var isLocallyDeleted: Bool?

        public init(
            url: String,
            name: String,
            mode: ProcessingMode,
            lastFetched: Int64 = 0,
            maxArticles: Int = 0,
            isEnabled: Bool = true,
            createdAt: Date = Date(),
            serverUpdatedAt: Date? = nil,
            locallyModified: Bool = false,
            serverId: String? = nil,
            serverVersion: Int64? = nil,
            mutationRevision: Int64 = 0,
            isLocallyDeleted: Bool = false
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
            self.serverId = serverId
            self.serverVersion = serverVersion
            self.mutationRevision = mutationRevision
            self.isLocallyDeleted = isLocallyDeleted
        }
    }

    @Model
    public final class Digest {
        /// Unique identifier for the digest
        @Attribute(.unique) public var id: UUID

        /// Timestamp when the digest was generated
        public var generatedAt: Date

        /// File path to the generated EPUB file
        public var epubFilePath: String

        /// Number of articles included in the digest
        public var articleCount: Int

        /// Number of briefing articles in the digest
        public var briefingCount: Int

        /// Number of full-content articles in the digest
        public var deepDiveCount: Int

        /// How the digest was triggered
        public var triggerType: TriggerType

        /// Total size of the EPUB file in bytes
        public var fileSizeBytes: Int64

        /// Whether the digest generation completed successfully
        public var isComplete: Bool

        /// Error message if generation failed
        public var errorMessage: String?

        // MARK: - Ghostwriter Sync Fields

        /// Remote ID from Ghostwriter server (nil if locally generated)
        public var remoteId: String?

        /// Period of the digest (morning, noon, evening, manual)
        public var period: String?

        /// Relationship to articles in this digest
        @Relationship(deleteRule: .cascade, inverse: \DigestArticle.digest)
        public var articles: [DigestArticle]

        public init(
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
    public final class DigestArticle {
        /// Unique identifier for the digest article
        @Attribute(.unique) public var id: UUID

        /// The parent digest this article belongs to
        public var digest: Digest?

        /// Article title
        public var title: String

        /// Article author (may be empty)
        public var author: String

        /// Processed content (HTML or Markdown depending on processing mode)
        public var content: String

        /// Original article URL
        public var originalUrl: String

        /// Source feed URL
        public var feedUrl: String

        /// Source feed name
        public var feedName: String

        /// Type of content (briefing or deep dive)
        public var contentType: ContentType

        /// Timestamp when the article was published (if available)
        public var publishedAt: Date?

        /// Order/position in the digest (for sorting)
        public var orderIndex: Int

        /// Word count of the processed content
        public var wordCount: Int

        public init(
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

    @Model
    public final class FeedMutation {
        @Attribute(.unique) public var opId: String
        public var url: String
        public var scopeKey: String
        public var kind: String
        public var baseVersion: Int64?
        public var title: String?
        public var isActive: Bool?
        public var mode: String?
        public var maxArticles: Int?
        public var sequence: Int64
        public var localRevision: Int64
        public var status: String
        public var origin: String
        public var sent: Bool
        public var serverKind: String?
        public var serverId: String?
        public var serverVersion: Int64?
        public var serverTitle: String?
        public var serverIsActive: Bool?
        public var serverMode: String?
        public var serverMaxArticles: Int?
        public var rejectionCode: String?
        public var rejectionMessage: String?
        public var createdAt: Date

        public init(
            opId: String = UUID().uuidString.lowercased(),
            url: String,
            scopeKey: String,
            kind: String,
            baseVersion: Int64? = nil,
            title: String? = nil,
            isActive: Bool? = nil,
            mode: String? = nil,
            maxArticles: Int? = nil,
            sequence: Int64,
            localRevision: Int64,
            status: String = "pending",
            origin: String = "post_upgrade",
            sent: Bool = false,
            createdAt: Date = Date()
        ) {
            self.opId = opId
            self.url = url
            self.scopeKey = scopeKey
            self.kind = kind
            self.baseVersion = baseVersion
            self.title = title
            self.isActive = isActive
            self.mode = mode
            self.maxArticles = maxArticles
            self.sequence = sequence
            self.localRevision = localRevision
            self.status = status
            self.origin = origin
            self.sent = sent
            self.createdAt = createdAt
        }
    }

    @Model
    public final class FeedSyncState {
        @Attribute(.unique) public var key: String
        public var destinationURL: String?
        public var configurationId: String?
        public var serverInstanceId: String?
        public var cursorVersion: Int64?
        public var firstReconciliationComplete: Bool
        public var suspended: Bool
        public var generation: Int64
        public var nextSequence: Int64
        public var lastSuccessfulSync: Date?

        public init(
            key: String = "main",
            destinationURL: String? = nil,
            configurationId: String? = nil,
            serverInstanceId: String? = nil,
            cursorVersion: Int64? = nil,
            firstReconciliationComplete: Bool = false,
            suspended: Bool = false,
            generation: Int64 = 0,
            nextSequence: Int64 = 1,
            lastSuccessfulSync: Date? = nil
        ) {
            self.key = key
            self.destinationURL = destinationURL
            self.configurationId = configurationId
            self.serverInstanceId = serverInstanceId
            self.cursorVersion = cursorVersion
            self.firstReconciliationComplete = firstReconciliationComplete
            self.suspended = suspended
            self.generation = generation
            self.nextSequence = nextSequence
            self.lastSuccessfulSync = lastSuccessfulSync
        }
    }
}
