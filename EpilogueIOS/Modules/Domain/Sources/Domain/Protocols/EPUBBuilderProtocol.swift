//
//  EPUBBuilderProtocol.swift
//  Domain
//

import Foundation

public protocol EPUBBuilderProtocol: Sendable {
    func generateEPUB(
        articles: [ProcessedArticle],
        outputPath: String,
        date: Date
    ) throws -> URL
}
