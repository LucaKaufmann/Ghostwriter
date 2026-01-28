//
//  Feed.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import SwiftData

/// Represents an RSS/Atom feed that the user has subscribed to.
/// This model is persisted using SwiftData.
@Model
public final class Feed {
    /// The feed URL (primary identifier)
    @Attribute(.unique) public var url: String

    /// User-provided name for the feed
    public var name: String

    /// Processing mode for articles from this feed
    public var mode: ProcessingMode

    /// Timestamp of last successful fetch (milliseconds since epoch)
    public var lastFetched: Int64

    /// Maximum number of articles to fetch per digest (0 = unlimited)
    public var maxArticles: Int

    /// Whether this feed is currently enabled
    public var isEnabled: Bool

    /// Timestamp when this feed was added
    public var createdAt: Date

    // MARK: - Ghostwriter Sync Fields

    /// Timestamp of when the server last updated this feed (for sync)
    public var serverUpdatedAt: Date?

    /// Whether this feed has been modified locally and needs to be synced
    public var locallyModified: Bool

    public init(
        url: String,
        name: String,
        mode: ProcessingMode,
        lastFetched: Int64 = 0,
        maxArticles: Int = 0,
        isEnabled: Bool = true,
        createdAt: Date = Date(),
        serverUpdatedAt: Date? = nil,
        locallyModified: Bool = false
    ) {
        self.url = url
        self.name = name
        self.mode = mode
        self.lastFetched = lastFetched
        self.maxArticles = maxArticles
        self.isEnabled = isEnabled
        self.createdAt = createdAt
        self.serverUpdatedAt = serverUpdatedAt
        self.locallyModified = locallyModified
    }
}
