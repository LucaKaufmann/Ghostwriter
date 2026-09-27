import Foundation
import SwiftData

/// Binding, cursor, and allocator committed with feed and outbox changes.
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
