import Foundation
import Domain
import SwiftData
import EpilogueShared

private final class IOSFeedV2ConfigurationAdapter: NSObject, FeedV2ConfigurationPort {
    private let settings: SettingsRepositoryProtocol
    private let engine: IOSFeedV2StoreEngine

    @MainActor init(settings: SettingsRepositoryProtocol, engine: IOSFeedV2StoreEngine) {
        self.settings = settings
        self.engine = engine
    }

    func currentDestination(
        completionHandler: @escaping (FeedV2Destination?, Error?) -> Void
    ) {
        Task { @MainActor in
            do {
                guard try await settings.isGhostwriterConfigured(),
                      let url = try await settings.getGhostwriterURL() else {
                    completionHandler(nil, nil)
                    return
                }
                completionHandler(try engine.destination(for: url), nil)
            } catch {
                completionHandler(nil, error)
            }
        }
    }
}

@MainActor
final class SharedFeedV2Bridge {
    enum Outcome {
        case complete(applied: Int, pulled: Int)
        case partial(pending: Int, conflicts: Int, rejected: Int, phase: String?)
        case notConfigured
        case upgradeRequired
        case serverChanged
        case failed(phase: String, message: String)
    }

    let store: IOSFeedV2StorePortAdapter
    private let configuration: IOSFeedV2ConfigurationAdapter
    private let settings: SettingsRepositoryProtocol

    init(settings: SettingsRepositoryProtocol, container: ModelContainer) {
        self.settings = settings
        self.store = IOSFeedV2StorePortAdapter(container: container)
        self.configuration = IOSFeedV2ConfigurationAdapter(settings: settings, engine: store.engine)
    }

    func sync() async throws -> Outcome {
        guard try await settings.isGhostwriterConfigured(),
              let url = try await settings.getGhostwriterURL() else {
            return .notConfigured
        }
        let key = try await settings.getGhostwriterAPIKey()
        let handle = GhostwriterClientHandle.companion.create(baseUrl: url, apiKey: key)
        defer { handle.close() }
        let useCase = FeedSyncV2UseCase(configuration: configuration,
                                       store: store, remote: handle.client)
        return try await run(useCase: useCase)
    }

    func run(useCase: FeedSyncV2UseCase) async throws -> Outcome {
        try Task.checkCancellation()
        let result = try await useCase.sync()
        // Kotlin/Native's exported suspend overlay does not guarantee that a
        // cancelled Swift task interrupts an already suspended transport.
        // Never turn its eventual success into an app-level sync success.
        try Task.checkCancellation()
        switch result {
        case let complete as FeedSyncV2Outcome.Complete:
            return .complete(applied: Int(complete.applied), pulled: Int(complete.pulled))
        case let partial as FeedSyncV2Outcome.Partial:
            return .partial(pending: Int(partial.pending),
                            conflicts: Int(partial.conflicts),
                            rejected: Int(partial.rejected), phase: partial.phase)
        case _ as FeedSyncV2Outcome.NotConfigured:
            return .notConfigured
        case _ as FeedSyncV2Outcome.ServerUpgradeRequired:
            return .upgradeRequired
        case _ as FeedSyncV2Outcome.ServerChanged:
            return .serverChanged
        case let failed as FeedSyncV2Outcome.Failed:
            return .failed(phase: failed.phase, message: failed.message)
        default:
            return .failed(phase: "sync", message: "Unexpected feed sync outcome")
        }
    }
}
