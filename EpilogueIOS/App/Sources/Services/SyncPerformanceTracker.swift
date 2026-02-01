//
//  SyncPerformanceTracker.swift
//  Epilogue
//
//  Created on 2026-02-01.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import OSLog
import os

/// Thread-safe performance tracker for Ghostwriter sync operations.
/// Uses OSLog and OSSignpost for Instruments integration.
public final class SyncPerformanceTracker: @unchecked Sendable {

    // MARK: - Types

    public struct OperationMetrics: Sendable {
        public let label: String
        public let durationMs: Double
        public let bytesTransferred: Int?
    }

    // MARK: - Properties

    private let logger = Logger(subsystem: "com.epilogue", category: "SyncPerformance")
    private let signposter = OSSignposter(subsystem: "com.epilogue", category: "SyncPerformance")

    private let lock = NSLock()
    private var operations: [OperationMetrics] = []
    private let syncStart: ContinuousClock.Instant
    private var totalBytesDownloaded: Int = 0
    private var totalArticlesSynced: Int = 0

    // MARK: - Init

    public init() {
        self.syncStart = ContinuousClock.now
        logger.info("Sync performance tracking started")
    }

    // MARK: - Signpost intervals

    /// Begin a signpost interval. Returns a state to pass to `endInterval`.
    public func beginInterval(_ label: String) -> (OSSignpostIntervalState, ContinuousClock.Instant) {
        let state = signposter.beginInterval("SyncOperation", "\(label)")
        logger.debug("▶ \(label)")
        return (state, ContinuousClock.now)
    }

    /// End a signpost interval and record the operation.
    @discardableResult
    public func endInterval(_ label: String, state: (OSSignpostIntervalState, ContinuousClock.Instant), bytes: Int? = nil) -> Double {
        signposter.endInterval("SyncOperation", state.0, "\(label) done")
        let elapsed = ContinuousClock.now - state.1
        let ms = elapsed.milliseconds
        let metric = OperationMetrics(label: label, durationMs: ms, bytesTransferred: bytes)
        lock.withLock {
            operations.append(metric)
            if let b = bytes { totalBytesDownloaded += b }
        }
        if let bytes {
            logger.debug("◼ \(label): \(String(format: "%.1f", ms))ms (\(Self.formatBytes(bytes)))")
        } else {
            logger.debug("◼ \(label): \(String(format: "%.1f", ms))ms")
        }
        return ms
    }

    // MARK: - Counters

    public func addArticlesSynced(_ count: Int) {
        lock.withLock { totalArticlesSynced += count }
    }

    public func addBytesDownloaded(_ bytes: Int) {
        lock.withLock { totalBytesDownloaded += bytes }
    }

    // MARK: - Summary

    public func logSummary() {
        let totalMs = (ContinuousClock.now - syncStart).milliseconds
        let snapshot: ([OperationMetrics], Int, Int) = lock.withLock {
            (operations, totalBytesDownloaded, totalArticlesSynced)
        }

        logger.info("╔══════════════════════════════════════")
        logger.info("║ Sync Performance Summary")
        logger.info("║ Total duration: \(String(format: "%.1f", totalMs))ms")
        logger.info("║ Operations: \(snapshot.0.count)")
        logger.info("║ Total bytes downloaded: \(Self.formatBytes(snapshot.1))")
        logger.info("║ Total articles synced: \(snapshot.2)")

        for op in snapshot.0 {
            if let bytes = op.bytesTransferred {
                logger.info("║  · \(op.label): \(String(format: "%.1f", op.durationMs))ms (\(Self.formatBytes(bytes)))")
            } else {
                logger.info("║  · \(op.label): \(String(format: "%.1f", op.durationMs))ms")
            }
        }
        logger.info("╚══════════════════════════════════════")
    }

    // MARK: - Helpers

    static func formatBytes(_ bytes: Int) -> String {
        if bytes < 1024 {
            return "\(bytes) B"
        } else {
            return String(format: "%.1f KB", Double(bytes) / 1024.0)
        }
    }
}

// MARK: - Duration extension

private extension Duration {
    var milliseconds: Double {
        let (seconds, attoseconds) = self.components
        return Double(seconds) * 1000.0 + Double(attoseconds) / 1_000_000_000_000_000.0
    }
}
