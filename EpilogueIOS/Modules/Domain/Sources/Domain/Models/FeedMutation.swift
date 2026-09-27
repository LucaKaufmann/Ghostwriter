import Foundation
import SwiftData

/// One durable local proposal or frozen v2 operation for an exact feed URL.
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
