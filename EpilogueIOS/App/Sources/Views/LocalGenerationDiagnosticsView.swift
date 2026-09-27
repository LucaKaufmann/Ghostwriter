import SwiftUI
import Domain

struct LocalGenerationDiagnosticsView: View {
    @ObservedObject var service: LocalDigestService

    var body: some View {
        if let outcome = service.lastGenerationOutcome,
           let diagnostics = service.lastGenerationDiagnostics {
            VStack(alignment: .leading, spacing: 5) {
                Text(service.generationStatus)
                    .font(.footnote.weight(.semibold))
                Text("\(diagnostics.deliveredCount) included · \(diagnostics.filteredCount) filtered · \(diagnostics.deferredCount) deferred · \(diagnostics.failedCount) issues")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let code = diagnostics.runError {
                    Text(code.replacingOccurrences(of: "_", with: " "))
                        .font(.caption)
                }
                if outcome == .partial || outcome == .failed {
                    ForEach(Array(diagnostics.feeds.enumerated()), id: \.offset) { index, feed in
                        if let code = feed.feedError {
                            Text("Source \(index + 1): \(code.replacingOccurrences(of: "_", with: " "))")
                                .font(.caption)
                        }
                        ForEach(Array(feed.failedItems.enumerated()), id: \.offset) { _, item in
                            Text("\(item.stage): \(item.code.replacingOccurrences(of: "_", with: " "))")
                                .font(.caption)
                        }
                    }
                }
            }
            .accessibilityElement(children: .combine)
        }
    }
}
