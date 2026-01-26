//
//  OpenAIService.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import Domain

/// OpenAI implementation of AIServiceProtocol
public final class OpenAIService: AIServiceProtocol {
    public let provider: AIProvider = .openAI

    private let apiKey: String
    private let model: String
    private let session: URLSession
    private let endpoint = "https://api.openai.com/v1/chat/completions"

    public init(apiKey: String, model: String = "gpt-4o-mini", session: URLSession = .shared) {
        self.apiKey = apiKey
        self.model = model
        self.session = session
    }

    public func summarize(title: String, content: String, author: String?) async throws -> String {
        guard !apiKey.isEmpty else {
            throw AIServiceError.missingAPIKey
        }

        let prompt = buildPrompt(title: title, content: content, author: author)

        let requestBody = OpenAIRequest(
            model: model,
            messages: [
                Message(role: "system", content: systemPrompt),
                Message(role: "user", content: prompt)
            ],
            temperature: 0.7,
            maxTokens: 500
        )

        guard let url = URL(string: endpoint) else {
            throw AIServiceError.invalidResponse
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(requestBody)

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw AIServiceError.networkError("Invalid response")
        }

        switch httpResponse.statusCode {
        case 200...299:
            let openAIResponse = try JSONDecoder().decode(OpenAIResponse.self, from: data)
            guard let summary = openAIResponse.choices.first?.message.content else {
                throw AIServiceError.invalidResponse
            }
            return summary.trimmingCharacters(in: .whitespacesAndNewlines)

        case 401:
            throw AIServiceError.invalidAPIKey

        case 429:
            throw AIServiceError.rateLimitExceeded

        default:
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw AIServiceError.networkError(errorMessage)
        }
    }

    public func validateConfiguration() async throws -> Bool {
        guard !apiKey.isEmpty else {
            return false
        }

        // Make a minimal test request
        let testRequest = OpenAIRequest(
            model: model,
            messages: [Message(role: "user", content: "Test")],
            temperature: 0.7,
            maxTokens: 5
        )

        guard let url = URL(string: endpoint) else {
            return false
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(testRequest)

        do {
            let (_, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                return false
            }
            return (200...299).contains(httpResponse.statusCode)
        } catch {
            return false
        }
    }

    // MARK: - Private Helpers

    private var systemPrompt: String {
        """
        You are a neutral editor creating concise briefings from articles. \
        Your summaries should be factual, balanced, and well-structured.

        Format your response in Markdown with three sections:

        **Hook** (1-2 sentences)
        A compelling opening that captures the article's main point.

        **Key Details**
        - Bullet points of the most important facts
        - Include relevant data, names, and context
        - 3-5 bullets maximum

        **Significance** (1-2 sentences)
        Why this matters and potential implications.

        Keep the total summary under 250 words. Use clear, professional language.
        """
    }

    private func buildPrompt(title: String, content: String, author: String?) -> String {
        var prompt = "Summarize the following article:\n\n"
        prompt += "**Title:** \(title)\n"

        if let author = author, !author.isEmpty {
            prompt += "**Author:** \(author)\n"
        }

        prompt += "\n**Content:**\n\(content)"

        return prompt
    }
}

// MARK: - Models

struct OpenAIRequest: Codable {
    let model: String
    let messages: [Message]
    let temperature: Double
    let maxTokens: Int

    enum CodingKeys: String, CodingKey {
        case model
        case messages
        case temperature
        case maxTokens = "max_tokens"
    }
}

struct Message: Codable {
    let role: String
    let content: String
}

struct OpenAIResponse: Codable {
    let choices: [Choice]
}

struct Choice: Codable {
    let message: Message
}
