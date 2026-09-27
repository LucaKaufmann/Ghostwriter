import SwiftData

public enum EpilogueSchemaV3: VersionedSchema {
    public static var versionIdentifier = Schema.Version(3, 0, 0)
    public static var models: [any PersistentModel.Type] {
        [Feed.self, Digest.self, DigestArticle.self, FeedMutation.self, FeedSyncState.self,
         ArticleDelivery.self, GenerationRun.self]
    }
}
