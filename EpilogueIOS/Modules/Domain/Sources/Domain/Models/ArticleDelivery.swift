import Foundation
import SwiftData

/// Installation-local delivery state for one exact feed URL and article key.
@Model
public final class ArticleDelivery {
    @Attribute(.unique) public var identity: String
    public var feedUrl: String
    public var articleKey: String
    public var state: String
    public var reason: String?
    public var filterSignature: String?
    public var lastAttemptSequence: Int64
    public var firstDigestId: UUID?
    public var committedAt: Date?

    public init(feedUrl: String, articleKey: String, state: String = "retryable",
                reason: String? = nil, filterSignature: String? = nil,
                lastAttemptSequence: Int64 = 0, firstDigestId: UUID? = nil,
                committedAt: Date? = nil) {
        // Length-prefixing preserves the exact feed URL without ambiguity.
        self.identity = "\(feedUrl.utf8.count):\(feedUrl)\(articleKey)"
        self.feedUrl = feedUrl
        self.articleKey = articleKey
        self.state = state
        self.reason = reason
        self.filterSignature = filterSignature
        self.lastAttemptSequence = lastAttemptSequence
        self.firstDigestId = firstDigestId
        self.committedAt = committedAt
    }
}
