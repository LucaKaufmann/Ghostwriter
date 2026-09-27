import SwiftData
import Domain
import GhostwriterClient

public enum EpilogueMigrationPlan: SchemaMigrationPlan {
    public static var schemas: [any VersionedSchema.Type] {
        [EpilogueSchemaV1.self, EpilogueSchemaV2.self, EpilogueSchemaV3.self]
    }

    public static var stages: [MigrationStage] {
        [.custom(fromVersion: EpilogueSchemaV1.self,
                 toVersion: EpilogueSchemaV2.self,
                 willMigrate: nil,
                 didMigrate: { context in
            let feeds = try context.fetch(FetchDescriptor<EpilogueSchemaV2.Feed>())
            var sequence: Int64 = 1
            for feed in feeds {
                feed.mutationRevision = 0
                feed.isLocallyDeleted = false
                guard !feed.url.hasPrefix("synthetic://") else { continue }
                // Every old feed is a proposal. The legacy dirty flag was not
                // reliably set by all edit paths, so it cannot decide intent.
                context.insert(EpilogueSchemaV2.FeedMutation(
                    url: feed.url,
                    scopeKey: "__unbound__",
                    kind: "upsert",
                    title: feed.name,
                    isActive: feed.isEnabled,
                    mode: feed.mode == .briefing ? "summarize" : "raw",
                    maxArticles: feed.maxArticles,
                    sequence: sequence,
                    localRevision: 0,
                    status: "needs_reconciliation",
                    origin: "legacy"))
                sequence += 1
            }
            context.insert(EpilogueSchemaV2.FeedSyncState(nextSequence: sequence))
            try context.save()
        }),
         .custom(fromVersion: EpilogueSchemaV2.self,
                 toVersion: EpilogueSchemaV3.self,
                 willMigrate: nil,
                 didMigrate: { context in
            // V2 DigestArticle stored both source fields. Only completed local
            // history can prove an article was delivered by this installation.
            let localDigests = try context.fetch(FetchDescriptor<Domain.Digest>())
                .filter { $0.isComplete && $0.remoteId == nil }
                .sorted {
                    if $0.generatedAt != $1.generatedAt {
                        return $0.generatedAt < $1.generatedAt
                    }
                    return $0.id.uuidString < $1.id.uuidString
                }
            var seen = Set<String>()
            for digest in localDigests {
                for article in digest.articles {
                    guard !article.feedUrl.isEmpty,
                          let identity = ArticleDeliveryIdentityBridge.identify(article.originalUrl)
                    else { continue }
                    let delivery = ArticleDelivery(
                        feedUrl: article.feedUrl, articleKey: identity.articleKey,
                        state: "delivered", firstDigestId: digest.id,
                        committedAt: digest.generatedAt)
                    guard seen.insert(delivery.identity).inserted else { continue }
                    context.insert(delivery)
                }
            }
            try context.save()
        })]
    }
}
