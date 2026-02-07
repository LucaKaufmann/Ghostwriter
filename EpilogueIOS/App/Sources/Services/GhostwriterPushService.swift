//
//  GhostwriterPushService.swift
//  Epilogue
//
//  Created on 2026-02-07.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import Data
import GhostwriterClient
import OSLog
import UIKit

enum GhostwriterPushService {
    private static let logger = Logger(subsystem: "com.epilogue", category: "GhostwriterPush")

    static func registerAPNsDeviceToken(_ deviceToken: Data) async {
        let settings = SettingsRepository()

        guard (try? await settings.isGhostwriterConfigured()) == true else { return }
        guard (try? await settings.isGhostwriterPushEnabled()) == true else { return }

        guard let url = try? await settings.getGhostwriterURL(), !url.isEmpty else { return }
        guard let apiKey = try? await settings.getGhostwriterAPIKey(), !apiKey.isEmpty else {
            logger.debug("Missing Ghostwriter API token; skipping push registration")
            return
        }

        let tokenHex = deviceToken.map { String(format: "%02x", $0) }.joined()
        guard !tokenHex.isEmpty else { return }

        let deviceId = (try? await settings.getGhostwriterDeviceId()) ?? UUID().uuidString.lowercased()

        let appVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
        let deviceModel = await MainActor.run { UIDevice.current.model }

        do {
            let client = try GhostwriterClient(baseURLString: url, apiKey: apiKey)
            _ = try await client.registerPushDevice(
                PushDeviceRegisterRequest(
                    deviceId: deviceId,
                    platform: "ios",
                    token: tokenHex,
                    appVersion: appVersion,
                    deviceModel: deviceModel
                )
            )
            logger.info("Registered device for push notifications")
        } catch {
            logger.warning("Push registration failed: \(error.localizedDescription)")
        }
    }

    static func unregisterCurrentDevice() async {
        let settings = SettingsRepository()

        guard let url = try? await settings.getGhostwriterURL(), !url.isEmpty else { return }
        guard let apiKey = try? await settings.getGhostwriterAPIKey(), !apiKey.isEmpty else { return }

        let deviceId = (try? await settings.getGhostwriterDeviceId()) ?? ""
        guard !deviceId.isEmpty else { return }

        do {
            let client = try GhostwriterClient(baseURLString: url, apiKey: apiKey)
            _ = try await client.unregisterPushDevice(deviceId: deviceId)
            logger.info("Unregistered device from push notifications")
        } catch {
            logger.warning("Push unregistration failed: \(error.localizedDescription)")
        }
    }
}
