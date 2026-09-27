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
import SwiftData

@MainActor
public final class LocalDigestService: ObservableObject {
    private let feedRepository: FeedRepositoryProtocol
    private let digestRepository: DigestRepositoryProtocol
    private let settingsRepository: SettingsRepositoryProtocol
    private let modelContainer: ModelContainer
    private let logger = Logger(subsystem: "com.epilogue", category: "LocalDigest")

    @Published public private(set) var isGenerating = false
    @Published public private(set) var generationError: Error?
    @Published public private(set) var lastGeneratedDigest: Domain.Digest?
    @Published public private(set) var generationStatus: String = ""
    @Published public private(set) var lastGenerationOutcome: LocalGenerationOutcome?
    @Published public private(set) var lastGenerationDiagnostics: GenerationDiagnostics?

    public init(
        feedRepository: FeedRepositoryProtocol,
        digestRepository: DigestRepositoryProtocol,
        settingsRepository: SettingsRepositoryProtocol,
        modelContainer: ModelContainer
    ) {
        self.feedRepository = feedRepository
        self.digestRepository = digestRepository
        self.settingsRepository = settingsRepository
        self.modelContainer = modelContainer
        if let run = try? DeliveryStore(container: modelContainer).latestRun(),
           let outcome = LocalGenerationOutcome(rawValue: run.outcome) {
            lastGenerationOutcome = outcome
            lastGenerationDiagnostics = try? JSONDecoder().decode(
                GenerationDiagnostics.self, from: Data(run.diagnosticsJSON.utf8))
            generationStatus = Self.description(outcome, lastGenerationDiagnostics)
        }
    }

    /// Generate a digest locally on device
    public func generateDigest(mode: LocalGenerationMode = .normal) async {
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
                feedRepository: feedRepository,
                aiService: aiService,
                minWordCount: minWordCount
            )

            let epubBuilder = EPUBBuilder()

            let digestGenerator = DigestGenerator(
                feedRepository: feedRepository,
                articleRepository: articleRepository,
                epubBuilder: epubBuilder,
                deliveryStore: DeliveryStore(container: modelContainer),
                filterSignature: DeliveryFilterSignature.make(minWordCount: minWordCount)
            )

            // Generate
            generationStatus = "Fetching and processing feeds..."
            logger.info("Starting digest generation pipeline")

            let result = try await digestGenerator.generateDigest(
                triggerType: .manual,
                period: "manual",
                mode: mode
            )

            lastGeneratedDigest = result.digest
            lastGenerationOutcome = result.outcome
            lastGenerationDiagnostics = result.diagnostics
            generationStatus = Self.description(result.outcome, result.diagnostics)
            if let digest = result.digest {
                logger.info("Local digest generation complete: \(digest.articleCount) articles")
                await CustomExportHelper.exportIfConfigured(
                    fileURL: URL(fileURLWithPath: digest.epubFilePath),
                    settingsRepository: settingsRepository
                )
            }

        } catch {
            generationError = error
            generationStatus = error is CancellationError ? "Generation cancelled" :
                "Failed: \(error.localizedDescription)"
            logger.error("Local digest generation failed: \(error.localizedDescription)")
        }

        isGenerating = false
    }

    private static func description(_ outcome: LocalGenerationOutcome,
                                    _ diagnostics: GenerationDiagnostics?) -> String {
        guard let diagnostics else { return outcome.rawValue.capitalized }
        let articleWord = diagnostics.deliveredCount == 1 ? "article" : "articles"
        let failureWord = diagnostics.failedCount == 1 ? "failure" : "failures"
        switch outcome {
        case .complete:
            return "Complete: \(diagnostics.deliveredCount) \(articleWord)"
        case .partial:
            return "Partial: \(diagnostics.deliveredCount) \(articleWord), \(diagnostics.failedCount) \(failureWord), \(diagnostics.deferredCount) deferred"
        case .empty:
            return "No new articles to include"
        case .deferred:
            return "No articles included; more remain for the next edition"
        case .failed:
            return "Generation failed: \(diagnostics.failedCount) \(diagnostics.failedCount == 1 ? "issue" : "issues")"
        case .cancelled:
            return "Generation cancelled"
        case .conflict:
            return "Another edition claimed these articles; retry generation"
        }
    }
}
