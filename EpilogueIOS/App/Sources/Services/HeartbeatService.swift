//
//  HeartbeatService.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import Domain
import Data
import GhostwriterClient
import OSLog

/// Service responsible for sending heartbeats to Ghostwriter server
///
/// Heartbeats:
/// - Indicate the app is active
/// - Prevent auto-disable of scheduled digest generation on the server
/// - Should be sent on app launch and periodically in background
@MainActor
public final class HeartbeatService {
    private let settingsRepository: SettingsRepositoryProtocol
    private let logger = Logger(subsystem: "com.epilogue", category: "Heartbeat")

    public init(settingsRepository: SettingsRepositoryProtocol) {
        self.settingsRepository = settingsRepository
    }

    /// Send a heartbeat to indicate the app is active
    /// - Returns: The heartbeat response with schedule status
    @discardableResult
    public func sendHeartbeat() async throws -> HeartbeatResponse {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            throw GhostwriterError.notConfigured
        }

        let client = try await createClient()
        let response = try await client.sendHeartbeat()

        logger.debug("Heartbeat sent: schedules_active=\(response.schedulesActive)")

        if let message = response.message {
            logger.info("Heartbeat message: \(message)")
        }

        return response
    }

    /// Get the current client status from the server
    public func getClientStatus() async throws -> ClientStatusResponse {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            throw GhostwriterError.notConfigured
        }

        let client = try await createClient()
        return try await client.getClientStatus()
    }

    /// Check server health
    public func checkHealth() async throws -> HealthResponse {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            throw GhostwriterError.notConfigured
        }

        let client = try await createClient()
        return try await client.checkHealth()
    }

    // MARK: - Private Helpers

    private func createClient() async throws -> GhostwriterClient {
        guard let url = try await settingsRepository.getGhostwriterURL() else {
            throw GhostwriterError.notConfigured
        }

        let apiKey = try await settingsRepository.getGhostwriterAPIKey()
        return try GhostwriterClient(baseURLString: url, apiKey: apiKey)
    }
}
