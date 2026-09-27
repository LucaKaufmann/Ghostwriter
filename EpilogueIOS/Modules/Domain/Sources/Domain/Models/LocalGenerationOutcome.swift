import Foundation

public enum LocalGenerationMode: String, Codable, Sendable {
    case normal
    case regenerate
}

public enum LocalGenerationOutcome: String, Codable, Sendable {
    case complete, partial, empty, deferred, failed, cancelled, conflict
}

/// A value copy of feed settings, safe to use across asynchronous fetch work.
public struct FeedGenerationSnapshot: Sendable {
    public let url: String
    public let name: String
    public let mode: ProcessingMode
    public let maxArticles: Int

    public init(url: String, name: String, mode: ProcessingMode, maxArticles: Int) {
        self.url = url
        self.name = name
        self.mode = mode
        self.maxArticles = maxArticles
    }
}

public struct GenerationItemError: Codable, Sendable {
    public let articleKey: String?
    public let url: String?
    public let stage: String
    public let code: String

    public init(articleKey: String?, url: String?, stage: String, code: String) {
        self.articleKey = articleKey
        self.url = url
        self.stage = stage
        self.code = code
    }
}

public struct FeedIngestionResult: Codable, Sendable {
    public let feedUrl: String
    public var candidateCount = 0
    public var selectedCount = 0
    public var deliveredCount = 0
    public var filteredCount = 0
    public var capDeferredCount = 0
    public var failedItems: [GenerationItemError] = []
    public var feedError: String?

    public init(feedUrl: String) { self.feedUrl = feedUrl }
}

public struct GenerationDiagnostics: Codable, Sendable {
    public var feeds: [FeedIngestionResult]
    public var runError: String?
    /// Explicit generation intent. Missing on V3 rows written before this field.
    public var mode: LocalGenerationMode?

    public init(feeds: [FeedIngestionResult], runError: String? = nil,
                mode: LocalGenerationMode? = nil) {
        self.feeds = feeds
        self.runError = runError
        self.mode = mode
    }

    private enum CodingKeys: String, CodingKey { case feeds, runError, mode }

    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        feeds = try values.decode([FeedIngestionResult].self, forKey: .feeds)
        runError = try values.decodeIfPresent(String.self, forKey: .runError)
        // A future mode must not discard otherwise valid feed diagnostics.
        // Unknown intent remains nil and recovery requires an own claim.
        mode = try? values.decode(LocalGenerationMode.self, forKey: .mode)
    }

    public func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(feeds, forKey: .feeds)
        try values.encodeIfPresent(runError, forKey: .runError)
        try values.encodeIfPresent(mode, forKey: .mode)
    }

    public var deliveredCount: Int { feeds.reduce(0) { $0 + $1.deliveredCount } }
    public var filteredCount: Int { feeds.reduce(0) { $0 + $1.filteredCount } }
    public var deferredCount: Int { feeds.reduce(0) { $0 + $1.capDeferredCount } }
    public var failedCount: Int {
        feeds.reduce(runError == nil ? 0 : 1) {
            $0 + $1.failedItems.count + ($1.feedError == nil ? 0 : 1)
        }
    }
}
