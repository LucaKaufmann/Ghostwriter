//
//  GhostwriterClientTests.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import XCTest
@testable import GhostwriterClient

final class GhostwriterClientTests: XCTestCase {
    
    // MARK: - Model Encoding Tests
    
    func testFeedSyncRequestEncoding() throws {
        let request = FeedSyncRequest(
            url: "https://example.com/feed",
            title: "Example Feed",
            isActive: true,
            mode: "summarize",
            maxArticles: 5
        )
        
        let encoder = JSONEncoder()
        let data = try encoder.encode(request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        
        XCTAssertEqual(json?["url"] as? String, "https://example.com/feed")
        XCTAssertEqual(json?["title"] as? String, "Example Feed")
        XCTAssertEqual(json?["is_active"] as? Bool, true)
        XCTAssertEqual(json?["mode"] as? String, "summarize")
        XCTAssertEqual(json?["max_articles"] as? Int, 5)
    }
    
    func testFeedResponseDecoding() throws {
        let json = """
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "url": "https://example.com/feed",
            "title": "Example Feed",
            "is_active": true,
            "mode": "raw",
            "max_articles": 10,
            "created_at": "2026-01-26T12:00:00",
            "updated_at": "2026-01-26T14:00:00"
        }
        """.data(using: .utf8)!
        
        let decoder = JSONDecoder()
        let response = try decoder.decode(FeedResponse.self, from: json)
        
        XCTAssertEqual(response.id, "123e4567-e89b-12d3-a456-426614174000")
        XCTAssertEqual(response.url, "https://example.com/feed")
        XCTAssertEqual(response.title, "Example Feed")
        XCTAssertEqual(response.isActive, true)
        XCTAssertEqual(response.mode, "raw")
        XCTAssertEqual(response.maxArticles, 10)
    }
    
    func testFeedChangesResponseDecoding() throws {
        let json = """
        {
            "feeds": [
                {
                    "id": "feed-1",
                    "url": "https://example.com/feed1",
                    "title": "Feed 1",
                    "is_active": true,
                    "mode": "raw",
                    "max_articles": 10,
                    "created_at": "2026-01-26T12:00:00",
                    "updated_at": "2026-01-26T14:00:00"
                }
            ],
            "tombstones": [
                {
                    "url": "https://example.com/deleted-feed",
                    "deleted_at": "2026-01-26T13:00:00"
                }
            ],
            "server_timestamp": "2026-01-26T15:00:00"
        }
        """.data(using: .utf8)!
        
        let decoder = JSONDecoder()
        let response = try decoder.decode(FeedChangesResponse.self, from: json)
        
        XCTAssertEqual(response.feeds.count, 1)
        XCTAssertEqual(response.feeds.first?.title, "Feed 1")
        XCTAssertEqual(response.tombstones.count, 1)
        XCTAssertEqual(response.tombstones.first?.url, "https://example.com/deleted-feed")
        XCTAssertEqual(response.serverTimestamp, "2026-01-26T15:00:00")
    }
    
    func testDigestResponseDecoding() throws {
        let json = """
        {
            "id": "digest-123",
            "filename": "2026-01-26_morning.epub",
            "available_formats": ["epub", "pdf"],
            "period": "morning",
            "status": "completed",
            "stage": null,
            "article_count": 15,
            "error_message": null,
            "created_at": "2026-01-26T07:00:00",
            "completed_at": "2026-01-26T07:05:00"
        }
        """.data(using: .utf8)!
        
        let decoder = JSONDecoder()
        let response = try decoder.decode(DigestResponse.self, from: json)
        
        XCTAssertEqual(response.id, "digest-123")
        XCTAssertEqual(response.filename, "2026-01-26_morning.epub")
        XCTAssertEqual(response.availableFormats ?? [], ["epub", "pdf"])
        XCTAssertEqual(response.period, "morning")
        XCTAssertEqual(response.status, "completed")
        XCTAssertEqual(response.articleCount, 15)
        XCTAssertTrue(response.isCompleted)
    }
    
    func testDigestStatusResponseDecoding() throws {
        let json = """
        {
            "id": "digest-123",
            "status": "processing",
            "stage": "enriching",
            "progress": {
                "total_feeds": 5,
                "feeds_fetched": 5,
                "total_articles": 20,
                "articles_enriched": 12
            },
            "started_at": "2026-01-26T07:00:00",
            "eta_seconds": 120
        }
        """.data(using: .utf8)!
        
        let decoder = JSONDecoder()
        let response = try decoder.decode(DigestStatusResponse.self, from: json)
        
        XCTAssertEqual(response.status, "processing")
        XCTAssertEqual(response.stage, "enriching")
        XCTAssertEqual(response.progress.totalArticles, 20)
        XCTAssertEqual(response.progress.articlesEnriched, 12)
        XCTAssertEqual(response.progress.progressPercentage, 0.6, accuracy: 0.01)
        XCTAssertFalse(response.isComplete)
    }
    
    func testHealthResponseDecoding() throws {
        let json = """
        {
            "status": "ok",
            "version": "1.0.0",
            "uptime_seconds": 3700,
            "last_successful_digest": "2026-01-26T07:00:00",
            "ai_provider": "ollama",
            "ai_model": "llama3.2"
        }
        """.data(using: .utf8)!
        
        let decoder = JSONDecoder()
        let response = try decoder.decode(HealthResponse.self, from: json)
        
        XCTAssertEqual(response.status, "ok")
        XCTAssertEqual(response.version, "1.0.0")
        XCTAssertEqual(response.uptimeSeconds, 3700)
        XCTAssertEqual(response.aiProvider, "ollama")
        XCTAssertTrue(response.isHealthy)
        XCTAssertEqual(response.formattedUptime, "1h 1m")
    }
    
    func testClientConfigResponseDecoding() throws {
        let json = """
        {
            "min_word_count": 300,
            "morning_hour": 7,
            "morning_minute": 0,
            "noon_hour": 12,
            "noon_minute": 0,
            "evening_hour": 18,
            "evening_minute": 30,
            "timezone": "Europe/Helsinki",
            "pdf_enabled": true,
            "pdf_page_size": "A4",
            "updated_at": "2026-01-26T15:00:00"
        }
        """.data(using: .utf8)!
        
        let decoder = JSONDecoder()
        let response = try decoder.decode(ClientConfigResponse.self, from: json)
        
        XCTAssertEqual(response.minWordCount, 300)
        XCTAssertEqual(response.morningHour, 7)
        XCTAssertEqual(response.eveningMinute, 30)
        XCTAssertEqual(response.timezone, "Europe/Helsinki")
        XCTAssertEqual(response.pdfEnabled, true)
        XCTAssertEqual(response.pdfPageSize, "A4")
    }
    
    // MARK: - Error Tests
    
    func testGhostwriterErrorDescriptions() {
        let notConfigured = GhostwriterError.notConfigured
        XCTAssertTrue(notConfigured.errorDescription?.contains("not configured") ?? false)
        
        let httpError = GhostwriterError.httpError(statusCode: 500, message: "Internal error")
        XCTAssertTrue(httpError.errorDescription?.contains("500") ?? false)
        
        let conflict = GhostwriterError.conflict(message: "Modified by another client")
        XCTAssertTrue(conflict.errorDescription?.contains("Conflict") ?? false)
    }
    
    // MARK: - Client Initialization Tests
    
    func testClientInitializationWithValidURL() throws {
        let client = try GhostwriterClient(baseURLString: "https://ghostwriter.example.com", apiKey: "test-key")
        XCTAssertNotNil(client)
    }
    
    func testClientInitializationWithInvalidURL() {
        XCTAssertThrowsError(try GhostwriterClient(baseURLString: "not a valid url")) { error in
            guard case GhostwriterError.invalidURL = error else {
                XCTFail("Expected invalidURL error")
                return
            }
        }
    }
}
