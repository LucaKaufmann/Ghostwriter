import SwiftData

public enum EpilogueSchemaV2: VersionedSchema {
    public static var versionIdentifier = Schema.Version(2, 0, 0)
    public static var models: [any PersistentModel.Type] {
        [Feed.self, Digest.self, DigestArticle.self, FeedMutation.self, FeedSyncState.self]
    }
}
