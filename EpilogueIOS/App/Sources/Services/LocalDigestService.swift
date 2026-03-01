//
//  LocalDigestService.swift
//  Epilogue
//
//  Wires up DigestGenerator with all its dependencies for local digest generation.
//

import Foundation
import OSLog
import Domain
import Data
import ContentProcessing
import EPUBGeneration
import AIServices

@MainActor
public final class LocalDigestService: ObservableObject {
    private let feedRepository: FeedRepositoryProtocol
    private let digestRepository: DigestRepositoryProtocol
    private let settingsRepository: SettingsRepositoryProtocol
    private let logger = Logger(subsystem: "com.epilogue", category: "LocalDigest")

    @Published public private(set) var isGenerating = false
    @Published public private(set) var generationError: Error?
    @Published public private(set) var lastGeneratedDigest: Digest?
    @Published public private(set) var generationStatus: String = ""

    public init(
        feedRepository: FeedRepositoryProtocol,
        digestRepository: DigestRepositoryProtocol,
        settingsRepository: SettingsRepositoryProtocol
    ) {
        self.feedRepository = feedRepository
        self.digestRepository = digestRepository
        self.settingsRepository = settingsRepository
    }

    /// Generate a digest locally on device
    public func generateDigest() async {
        guard !isGenerating else {
            logger.warning("Generation already in progress")
            return
        }

        isGenerating = true
        generationError = nil
        generationStatus = "Starting digest generation..."
        logger.info("Starting local digest generation")

        do {
            // Build dependencies
            generationStatus = "Setting up..."
            logger.info("Building dependencies")

            let feedParser = EpilogueFeedParser()
            let contentExtractor = ContentExtractor()

            // Check if AI is configured for briefing mode
            let apiKey = try await settingsRepository.getOpenAIKey()
            let aiService: AIServiceProtocol?
            if let key = apiKey, !key.isEmpty {
                aiService = OpenAIService(apiKey: key)
                logger.info("AI service configured for briefing mode")
            } else {
                aiService = nil
                logger.info("No AI API key — briefing mode unavailable, fidelity only")
            }

            let minWordCount = try await settingsRepository.getMinWordCount()
            let articleRepository = ArticleRepository(
                feedParser: feedParser,
                contentExtractor: contentExtractor,
                aiService: aiService,
                minWordCount: minWordCount
            )

            let epubBuilder = EPUBBuilder()

            let digestGenerator = DigestGenerator(
                feedRepository: feedRepository,
                digestRepository: digestRepository,
                articleRepository: articleRepository,
                epubBuilder: epubBuilder
            )

            // Generate
            generationStatus = "Fetching and processing feeds..."
            logger.info("Starting digest generation pipeline")

            let digest = try await digestGenerator.generateDigest(
                triggerType: .manual,
                period: "manual"
            )

            lastGeneratedDigest = digest
            generationStatus = "Complete! \(digest.articleCount) articles"
            logger.info("Local digest generation complete: \(digest.articleCount) articles, path: \(digest.epubFilePath)")
            await CustomExportHelper.exportIfConfigured(
                fileURL: URL(fileURLWithPath: digest.epubFilePath),
                settingsRepository: settingsRepository
            )

        } catch {
            generationError = error
            generationStatus = "Failed: \(error.localizedDescription)"
            logger.error("Local digest generation failed: \(error.localizedDescription)")
        }

        isGenerating = false
    }
}
