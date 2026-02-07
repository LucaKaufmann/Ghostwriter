//
//  NotificationModels.swift
//  Epilogue
//
//  Created on 2026-02-07.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

// MARK: - Push Device Registration

public struct PushDeviceRegisterRequest: Codable, Sendable {
    public let deviceId: String
    public let platform: String
    public let token: String
    public let appVersion: String?
    public let deviceModel: String?

    public init(
        deviceId: String,
        platform: String,
        token: String,
        appVersion: String? = nil,
        deviceModel: String? = nil
    ) {
        self.deviceId = deviceId
        self.platform = platform
        self.token = token
        self.appVersion = appVersion
        self.deviceModel = deviceModel
    }

    enum CodingKeys: String, CodingKey {
        case platform, token
        case deviceId = "device_id"
        case appVersion = "app_version"
        case deviceModel = "device_model"
    }
}

public struct PushDeviceResponse: Codable, Sendable, Identifiable {
    public let id: String
    public let deviceId: String
    public let platform: String
    public let enabled: Bool
    public let disabledAt: String?
    public let appVersion: String?
    public let deviceModel: String?
    public let lastSeenAt: String
    public let createdAt: String
    public let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, platform, enabled
        case deviceId = "device_id"
        case disabledAt = "disabled_at"
        case appVersion = "app_version"
        case deviceModel = "device_model"
        case lastSeenAt = "last_seen_at"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

public struct StatusResponse: Codable, Sendable {
    public let status: String
    public let message: String?
}

