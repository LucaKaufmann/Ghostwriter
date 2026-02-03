//
//  KeychainService.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import Security

public protocol KeychainServiceProtocol: Sendable {
    func save(_ value: String, forKey key: String) throws
    func retrieve(forKey key: String) throws -> String?
    func delete(forKey key: String) throws
    func deleteAll() throws
}

/// Service for secure storage of sensitive data using the iOS Keychain
public final class KeychainService: KeychainServiceProtocol, Sendable {
    private let serviceName: String

    public init(serviceName: String = "com.epilogue.app") {
        self.serviceName = serviceName
    }

    /// Save a string value to the Keychain
    /// - Parameters:
    ///   - value: The string value to save
    ///   - key: The key to associate with the value
    /// - Throws: KeychainError if the operation fails
    public func save(_ value: String, forKey key: String) throws {
        guard let data = value.data(using: .utf8) else {
            throw KeychainError.invalidData
        }

        // Delete any existing item first
        try? delete(forKey: key)

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
        ]

        let status = SecItemAdd(query as CFDictionary, nil)

        guard status == errSecSuccess else {
            throw KeychainError.unableToSave(status: status)
        }
    }

    /// Retrieve a string value from the Keychain
    /// - Parameter key: The key associated with the value
    /// - Returns: The string value, or nil if not found
    /// - Throws: KeychainError if the operation fails
    public func retrieve(forKey key: String) throws -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        if status == errSecItemNotFound {
            return nil
        }

        guard status == errSecSuccess else {
            throw KeychainError.unableToRetrieve(status: status)
        }

        guard let data = result as? Data,
              let value = String(data: data, encoding: .utf8) else {
            throw KeychainError.invalidData
        }

        return value
    }

    /// Delete a value from the Keychain
    /// - Parameter key: The key associated with the value to delete
    /// - Throws: KeychainError if the operation fails
    public func delete(forKey key: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: key
        ]

        let status = SecItemDelete(query as CFDictionary)

        // Success or item not found are both acceptable outcomes
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainError.unableToDelete(status: status)
        }
    }

    /// Update an existing value in the Keychain
    /// - Parameters:
    ///   - value: The new string value
    ///   - key: The key associated with the value
    /// - Throws: KeychainError if the operation fails
    public func update(_ value: String, forKey key: String) throws {
        guard let data = value.data(using: .utf8) else {
            throw KeychainError.invalidData
        }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: key
        ]

        let attributes: [String: Any] = [
            kSecValueData as String: data
        ]

        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)

        if status == errSecItemNotFound {
            // Item doesn't exist, create it instead
            try save(value, forKey: key)
            return
        }

        guard status == errSecSuccess else {
            throw KeychainError.unableToUpdate(status: status)
        }
    }

    /// Check if a value exists in the Keychain
    /// - Parameter key: The key to check
    /// - Returns: True if the key exists, false otherwise
    public func exists(forKey key: String) -> Bool {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: key,
            kSecReturnData as String: false
        ]

        let status = SecItemCopyMatching(query as CFDictionary, nil)
        return status == errSecSuccess
    }

    /// Delete all values from the Keychain for this service
    /// - Throws: KeychainError if the operation fails
    public func deleteAll() throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceName
        ]

        let status = SecItemDelete(query as CFDictionary)

        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainError.unableToDelete(status: status)
        }
    }
}

// MARK: - Errors

public enum KeychainError: LocalizedError {
    case invalidData
    case unableToSave(status: OSStatus)
    case unableToRetrieve(status: OSStatus)
    case unableToUpdate(status: OSStatus)
    case unableToDelete(status: OSStatus)

    public var errorDescription: String? {
        switch self {
        case .invalidData:
            return "Invalid data format"
        case .unableToSave(let status):
            return "Unable to save to Keychain (status: \(status))"
        case .unableToRetrieve(let status):
            return "Unable to retrieve from Keychain (status: \(status))"
        case .unableToUpdate(let status):
            return "Unable to update Keychain (status: \(status))"
        case .unableToDelete(let status):
            return "Unable to delete from Keychain (status: \(status))"
        }
    }
}
