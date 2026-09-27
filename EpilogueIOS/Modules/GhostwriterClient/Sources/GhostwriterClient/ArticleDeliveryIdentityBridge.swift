import Foundation
import EpilogueShared

/// Plain Swift value returned by the one framework that owns the KMP runtime.
public struct LocalArticleIdentity: Sendable, Equatable {
    public let normalizedURL: String
    public let articleKey: String

    public init(normalizedURL: String, articleKey: String) {
        self.normalizedURL = normalizedURL
        self.articleKey = articleKey
    }
}

public enum ArticleDeliveryIdentityBridge {
    public static func identify(_ link: String?) -> LocalArticleIdentity? {
        guard let valid = ArticleDeliveryIdentity()
            .fromArticleLink(link: link) as? ArticleIdentityResult.Valid else {
            return nil
        }
        return LocalArticleIdentity(normalizedURL: valid.normalizedUrl,
                                    articleKey: valid.articleKey)
    }
}
