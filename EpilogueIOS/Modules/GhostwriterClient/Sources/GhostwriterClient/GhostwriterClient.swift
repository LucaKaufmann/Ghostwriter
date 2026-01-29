//
//  GhostwriterClient.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Client for interacting with the Ghostwriter backend API
public actor GhostwriterClient {
    
    // MARK: - Properties
    
    private let baseURL: URL
    private let apiKey: String?
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    
    // MARK: - Initialization
    
    /// Create a new Ghostwriter client
    /// - Parameters:
    ///   - baseURL: The base URL of the Ghostwriter server
    ///   - apiKey: Optional API key for authentication
    ///   - session: URLSession to use for requests (defaults to shared)
    public init(baseURL: URL, apiKey: String? = nil, session: URLSession = .shared) {
        // Ensure base URL includes /api/ path
        if baseURL.pathComponents.contains("api") {
            self.baseURL = baseURL
        } else {
            self.baseURL = baseURL.appendingPathComponent("api")
        }
        self.apiKey = apiKey
        self.session = session
        
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
    }
    
    /// Convenience initializer from URL string
    public init(baseURLString: String, apiKey: String? = nil) throws {
        guard let url = URL(string: baseURLString) else {
            throw GhostwriterError.invalidURL(baseURLString)
        }
        self.init(baseURL: url, apiKey: apiKey)
    }
    
    // MARK: - Health
    
    /// Check the health of the Ghostwriter server
    public func checkHealth() async throws -> HealthResponse {
        return try await get(path: "/health", authenticated: false)
    }
    
    // MARK: - Feeds
    
    /// List all configured feeds
    public func listFeeds() async throws -> [FeedResponse] {
        return try await get(path: "/feeds")
    }
    
    /// Sync feeds to the server (additive merge)
    /// - Parameter feeds: List of feeds to sync
    /// - Returns: Sync results showing created/updated/unchanged counts
    public func syncFeeds(_ feeds: [FeedSyncRequest]) async throws -> FeedSyncResponse {
        return try await post(path: "/feeds/sync", body: feeds)
    }
    
    /// Get feed changes for incremental sync
    /// - Parameter since: Optional timestamp to get changes since
    /// - Returns: Feed changes including updated feeds and tombstones
    public func getFeedChanges(since: Date? = nil) async throws -> FeedChangesResponse {
        var queryItems: [URLQueryItem] = []
        
        if let since = since {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]
            queryItems.append(URLQueryItem(name: "since", value: formatter.string(from: since)))
        }
        
        return try await get(path: "/feeds/changes", queryItems: queryItems)
    }
    
    /// Delete a feed by URL
    /// - Parameter url: The feed URL to delete
    public func deleteFeed(byURL url: String) async throws {
        guard let encodedURL = url.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) else {
            throw GhostwriterError.invalidURL(url)
        }
        
        let _: EmptyResponse = try await delete(path: "/feeds/by-url/\(encodedURL)")
    }
    
    // MARK: - Digests
    
    /// List available digests
    /// - Parameters:
    ///   - limit: Maximum number of digests to return
    ///   - offset: Offset for pagination
    ///   - status: Optional status filter
    /// - Returns: List of digests
    public func listDigests(limit: Int = 20, offset: Int = 0, status: String? = nil) async throws -> [DigestResponse] {
        var queryItems = [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset))
        ]
        
        if let status = status {
            queryItems.append(URLQueryItem(name: "status", value: status))
        }
        
        return try await get(path: "/digests", queryItems: queryItems)
    }
    
    /// Get the most recent completed digest
    public func getLatestDigest() async throws -> DigestResponse {
        return try await get(path: "/digests/latest")
    }
    
    /// Trigger a digest generation
    /// - Parameter period: The time period ("morning", "noon", "evening", "manual")
    /// - Returns: Trigger response with digest ID
    public func triggerDigest(period: String = "manual") async throws -> DigestTriggerResponse {
        let request = DigestTriggerRequest(period: period)
        return try await post(path: "/digests/trigger", body: request)
    }
    
    /// Get the status of a running digest job
    /// - Parameter id: The digest ID
    /// - Returns: Status including progress and ETA
    public func getDigestStatus(id: String) async throws -> DigestStatusResponse {
        return try await get(path: "/digests/\(id)/status")
    }
    
    /// Get all articles for a digest with their content
    /// - Parameter id: The digest ID
    /// - Returns: Articles response with full content
    public func getDigestArticles(id: String) async throws -> DigestArticlesResponse {
        return try await get(path: "/digests/\(id)/articles")
    }
    
    /// Download a digest EPUB file
    /// - Parameter filename: The EPUB filename
    /// - Returns: Raw EPUB data
    public func downloadDigest(filename: String) async throws -> Data {
        return try await getData(path: "/digests/\(filename)")
    }
    
    // MARK: - Schedules
    
    /// List all schedule configurations
    public func listSchedules() async throws -> [ScheduleResponse] {
        return try await get(path: "/schedules")
    }
    
    /// Update a schedule configuration
    /// - Parameters:
    ///   - period: The period to update ("morning", "noon", "evening")
    ///   - request: The update request
    /// - Returns: Updated schedule
    public func updateSchedule(period: String, request: ScheduleUpdateRequest) async throws -> ScheduleResponse {
        return try await put(path: "/schedules/\(period.lowercased())", body: request)
    }
    
    // MARK: - Client Activity
    
    /// Send a heartbeat to indicate the app is active
    public func sendHeartbeat() async throws -> HeartbeatResponse {
        return try await post(path: "/client/heartbeat", body: EmptyRequest())
    }
    
    /// Get client status including activity tracking info
    public func getClientStatus() async throws -> ClientStatusResponse {
        return try await get(path: "/client/status")
    }
    
    // MARK: - Config
    
    /// Get the shared client configuration
    public func getConfig() async throws -> ClientConfigResponse {
        return try await get(path: "/config")
    }
    
    /// Update the shared client configuration
    /// - Parameter request: The configuration update request
    /// - Returns: Updated configuration
    public func updateConfig(_ request: ClientConfigUpdateRequest) async throws -> ClientConfigResponse {
        return try await put(path: "/config", body: request)
    }
    
    // MARK: - Private Helpers
    
    private func buildURL(path: String, queryItems: [URLQueryItem] = []) throws -> URL {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: true)
        
        if !queryItems.isEmpty {
            components?.queryItems = queryItems
        }
        
        guard let url = components?.url else {
            throw GhostwriterError.invalidURL(path)
        }
        
        return url
    }
    
    private func buildRequest(
        url: URL,
        method: String,
        body: Data? = nil,
        authenticated: Bool = true
    ) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        
        if authenticated, let apiKey = apiKey {
            request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        }
        
        if let body = body {
            request.httpBody = body
        }
        
        return request
    }
    
    private func performRequest<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw GhostwriterError.networkError(URLError(.badServerResponse))
        }
        
        try handleHTTPStatus(httpResponse, data: data)
        
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw GhostwriterError.decodingError(error)
        }
    }
    
    private func handleHTTPStatus(_ response: HTTPURLResponse, data: Data) throws {
        switch response.statusCode {
        case 200..<300:
            return // Success
        case 401:
            throw GhostwriterError.unauthorized
        case 404:
            let message = String(data: data, encoding: .utf8)
            throw GhostwriterError.notFound(message ?? "Resource not found")
        case 409:
            let message = String(data: data, encoding: .utf8) ?? "Conflict"
            if message.contains("digest") || message.contains("already") {
                throw GhostwriterError.digestInProgress
            }
            throw GhostwriterError.conflict(message: message)
        default:
            let message = String(data: data, encoding: .utf8)
            throw GhostwriterError.httpError(statusCode: response.statusCode, message: message)
        }
    }
    
    // MARK: - HTTP Methods
    
    private func get<T: Decodable>(
        path: String,
        queryItems: [URLQueryItem] = [],
        authenticated: Bool = true
    ) async throws -> T {
        let url = try buildURL(path: path, queryItems: queryItems)
        let request = buildRequest(url: url, method: "GET", authenticated: authenticated)
        return try await performRequest(request)
    }
    
    private func getData(path: String, authenticated: Bool = true) async throws -> Data {
        let url = try buildURL(path: path)
        let request = buildRequest(url: url, method: "GET", authenticated: authenticated)
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw GhostwriterError.networkError(URLError(.badServerResponse))
        }
        
        try handleHTTPStatus(httpResponse, data: data)
        
        return data
    }
    
    private func post<T: Decodable, B: Encodable>(
        path: String,
        body: B,
        authenticated: Bool = true
    ) async throws -> T {
        let url = try buildURL(path: path)
        
        let bodyData: Data
        do {
            bodyData = try encoder.encode(body)
        } catch {
            throw GhostwriterError.encodingError(error)
        }
        
        let request = buildRequest(url: url, method: "POST", body: bodyData, authenticated: authenticated)
        return try await performRequest(request)
    }
    
    private func put<T: Decodable, B: Encodable>(
        path: String,
        body: B,
        authenticated: Bool = true
    ) async throws -> T {
        let url = try buildURL(path: path)
        
        let bodyData: Data
        do {
            bodyData = try encoder.encode(body)
        } catch {
            throw GhostwriterError.encodingError(error)
        }
        
        let request = buildRequest(url: url, method: "PUT", body: bodyData, authenticated: authenticated)
        return try await performRequest(request)
    }
    
    private func delete<T: Decodable>(path: String, authenticated: Bool = true) async throws -> T {
        let url = try buildURL(path: path)
        let request = buildRequest(url: url, method: "DELETE", authenticated: authenticated)
        return try await performRequest(request)
    }
}

// MARK: - Helper Types

private struct EmptyRequest: Encodable {}

private struct EmptyResponse: Decodable {}
