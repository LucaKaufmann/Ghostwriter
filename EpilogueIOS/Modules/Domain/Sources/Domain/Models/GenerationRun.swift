import Foundation
import SwiftData

/// A local attempt remains observable even when it produced no EPUB.
@Model
public final class GenerationRun {
    @Attribute(.unique) public var runId: UUID
    public var attemptSequence: Int64
    public var startedAt: Date
    public var finishedAt: Date?
    public var trigger: String
    public var period: String?
    public var outcome: String
    public var digestId: UUID?
    public var diagnosticsJSON: String

    public init(runId: UUID = UUID(), attemptSequence: Int64,
                startedAt: Date = Date(), finishedAt: Date? = nil,
                trigger: String, period: String? = nil, outcome: String = "running",
                digestId: UUID? = nil, diagnosticsJSON: String = "{}") {
        self.runId = runId
        self.attemptSequence = attemptSequence
        self.startedAt = startedAt
        self.finishedAt = finishedAt
        self.trigger = trigger
        self.period = period
        self.outcome = outcome
        self.digestId = digestId
        self.diagnosticsJSON = diagnosticsJSON
    }
}
