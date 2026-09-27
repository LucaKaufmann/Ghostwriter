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

    public var deliveredCount: Int { feeds.reduce(0) { $0 + $1.deliveredCount } }
    public var filteredCount: Int { feeds.reduce(0) { $0 + $1.filteredCount } }
    public var deferredCount: Int { feeds.reduce(0) { $0 + $1.capDeferredCount } }
    public var failedCount: Int {
        feeds.reduce(runError == nil ? 0 : 1) {
            $0 + $1.failedItems.count + ($1.feedError == nil ? 0 : 1)
        }
    }
}
