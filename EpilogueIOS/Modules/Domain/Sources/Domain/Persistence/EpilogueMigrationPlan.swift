import SwiftData

public enum EpilogueMigrationPlan: SchemaMigrationPlan {
    public static var schemas: [any VersionedSchema.Type] {
        [EpilogueSchemaV1.self, EpilogueSchemaV2.self]
    }

    public static var stages: [MigrationStage] {
        [.custom(fromVersion: EpilogueSchemaV1.self,
                 toVersion: EpilogueSchemaV2.self,
                 willMigrate: nil,
                 didMigrate: { context in
            let feeds = try context.fetch(FetchDescriptor<Feed>())
            var sequence: Int64 = 1
            for feed in feeds {
                feed.mutationRevision = 0
                feed.isLocallyDeleted = false
                guard !feed.url.hasPrefix("synthetic://") else { continue }
                // Every old feed is a proposal. The legacy dirty flag was not
                // reliably set by all edit paths, so it cannot decide intent.
                context.insert(FeedMutation(
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
            context.insert(FeedSyncState(nextSequence: sequence))
            try context.save()
        })]
    }
}
