import Foundation
import SwiftData
import Domain
import Data
import GhostwriterClient
import OSLog

/// Sole iOS feed sync path. KMP v2 owns network sequencing; SwiftData owns commits.
@MainActor
public final class FeedSyncService {
    private let bridge: SharedFeedV2Bridge
    private let settingsRepository: SettingsRepositoryProtocol
    private let logger = Logger(subsystem: "com.epilogue", category: "FeedSync")
#if DEBUG
    var configuredURLReadForTesting: (() async throws -> String?)?
#endif

    public init(settingsRepository: SettingsRepositoryProtocol,
                modelContainer: ModelContainer) {
        self.settingsRepository = settingsRepository
        self.bridge = SharedFeedV2Bridge(settings: settingsRepository,
                                         container: modelContainer)
    }

    public func sync(tracker: SyncPerformanceTracker? = nil) async throws {
        let interval = tracker?.beginInterval("Feed Sync v2")
        let outcome = try await bridge.sync()
        if let interval { tracker?.endInterval("Feed Sync v2", state: interval) }
        try await apply(outcome)
    }

    func apply(_ outcome: SharedFeedV2Bridge.Outcome) async throws {
        switch outcome {
        case let .complete(applied, pulled):
            try Task.checkCancellation()
            try await settingsRepository.setLastFeedSyncTime(Date())
            logger.info("Feed sync v2 complete: applied=\(applied), pulled=\(pulled)")
        case .notConfigured:
            break
        case let .partial(pending, conflicts, rejected, phase):
            throw FeedSyncV2Error.partial(pending: pending, conflicts: conflicts,
                                          rejected: rejected, phase: phase)
        case .upgradeRequired:
            throw FeedSyncV2Error.upgradeRequired
        case .serverChanged:
            throw FeedSyncV2Error.serverChanged
        case let .failed(phase, message):
            throw FeedSyncV2Error.failed(phase: phase, message: message)
        }
    }

    public func addOrEdit(url: String, title: String, mode: ProcessingMode,
                          isEnabled: Bool, maxArticles: Int) throws {
        try bridge.store.engine.edit(url: url, title: title, mode: mode,
                                     isEnabled: isEnabled, maxArticles: maxArticles)
    }

    public func delete(url: String) throws {
        try bridge.store.engine.delete(url: url)
    }

    private func requireCurrentResolutionDestination() async throws {
        let generation = try bridge.store.engine.resolutionGeneration()
        let url: String?
#if DEBUG
        if let configuredURLReadForTesting {
            url = try await configuredURLReadForTesting()
        } else {
            url = try await settingsRepository.getGhostwriterURL()
        }
#else
        url = try await settingsRepository.getGhostwriterURL()
#endif
        try Task.checkCancellation()
        try bridge.store.engine.requireResolutionDestination(url, generation: generation)
    }

    func resolve(opId: String, action: IOSFeedV2StoreEngine.Resolution,
                 correctedTitle: String? = nil) async throws {
        try await requireCurrentResolutionDestination()
        try bridge.store.engine.resolve(opId: opId, action: action,
                                        correctedTitle: correctedTitle)
    }

    public func startNewBinding() throws {
        try bridge.store.engine.startNewBinding()
    }

    func resolvePrevious(opId: String,
                         action: IOSFeedV2StoreEngine.PreviousProposalAction) async throws {
        try await requireCurrentResolutionDestination()
        try bridge.store.engine.resolvePrevious(opId: opId, action: action)
    }

    public func suspendForDestinationChange(_ url: String?) throws {
        try bridge.store.engine.suspendForDestinationChange(url)
    }
}

public enum FeedSyncV2Error: LocalizedError {
    case partial(pending: Int, conflicts: Int, rejected: Int, phase: String?)
    case upgradeRequired
    case serverChanged
    case failed(phase: String, message: String)

    public var errorDescription: String? {
        switch self {
        case let .partial(pending, conflicts, rejected, phase):
            return "Feed sync needs attention: \(pending) pending, \(conflicts) conflicts, \(rejected) rejected" +
                (phase.map { " (\($0))" } ?? "")
        case .upgradeRequired:
            return "The server needs feed sync v2 before feeds can be synced."
        case .serverChanged:
            return "The server or destination changed. Review pending edits before reconnecting."
        case let .failed(phase, message):
            return "Feed sync \(phase) failed: \(message)"
        }
    }
}
