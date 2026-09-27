#if DEBUG
import Foundation
import SwiftData
import Domain

@MainActor
enum DeliveryUIFixture {
    static func seed(context: ModelContext, outcome: LocalGenerationOutcome) {
        do {
            let feed = FeedIngestionResult(feedUrl: "https://fixture.test/rss")
            var result = feed
            result.candidateCount = 5
            result.selectedCount = 2
            result.deliveredCount = [.complete, .partial].contains(outcome) ? 1 : 0
            result.filteredCount = outcome == .deferred ? 2 : 0
            result.capDeferredCount = [.complete, .empty, .failed].contains(outcome) ? 0 : 3
            if outcome == .partial {
                result.failedItems = [GenerationItemError(
                    articleKey: nil, url: nil, stage: "extraction", code: "extraction_failed")]
            } else if outcome == .failed {
                result.feedError = "fetch_failed"
            }
            let diagnostics = GenerationDiagnostics(feeds: [result])
            let json = String(data: try JSONEncoder().encode(diagnostics), encoding: .utf8) ?? "{}"
            context.insert(GenerationRun(attemptSequence: 1, trigger: "MANUAL", period: "manual",
                                         outcome: outcome.rawValue, diagnosticsJSON: json))
            try context.save()
        } catch {
            context.rollback()
            assertionFailure("Delivery UI fixture failed: \(error)")
        }
    }
}
#endif
