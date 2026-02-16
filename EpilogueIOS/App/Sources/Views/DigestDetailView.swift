//
//  DigestDetailView.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import SwiftUI
import SwiftData
import Domain

struct DigestDetailView: View {
    let digest: Digest
    private var dateFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, yyyy"
        return formatter
    }

    private var orderedArticles: [DigestArticle] {
        digest.articles.sorted { $0.orderIndex < $1.orderIndex }
    }

    var body: some View {
        EinkReaderView(
            articles: orderedArticles,
            epubFilePath: digest.epubFilePath,
            remoteDigestId: digest.remoteId
        )
        .navigationTitle(dateFormatter.string(from: digest.generatedAt))
        .navigationBarTitleDisplayMode(.inline)
    }

    private var scrollView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                // Briefings section
                if !orderedArticles.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Articles")
                            .font(.title2)
                            .fontWeight(.semibold)
                        Text("Grouped by feed in digest order")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.horizontal)
                    .padding(.top, 8)

                    ForEach(orderedArticles) { article in
                        ArticleCard(article: article)
                            .padding(.horizontal)
                    }
                }

                Spacer(minLength: 16)
            }
        }
    }

}

struct ArticleCard: View {
    let article: DigestArticle
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Title
            Text(article.title)
                .font(.headline)

            // Author
            if !article.author.isEmpty {
                Text("By \(article.author)")
                    .font(.caption)
                    .italic()
                    .foregroundStyle(.secondary)
            }

            // Feed name
            Text("From: \(article.feedName)")
                .font(.caption2)
                .foregroundStyle(.secondary)

            // Content
            if isExpanded {
                // Full content - render HTML as attributed string
                HTMLContentView(htmlContent: article.content)
                    .padding(.top, 4)

                Text("Tap to collapse")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            } else {
                // Preview
                Text(plainTextPreview)
                    .font(.subheadline)
                    .lineLimit(3)
                    .foregroundStyle(.primary)

                Text("Tap to expand")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.systemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color(.separator), lineWidth: 0.5)
        )
        .contentShape(Rectangle())
        .onTapGesture {
            withAnimation(.easeInOut(duration: 0.2)) {
                isExpanded.toggle()
            }
        }
    }

    private var plainTextPreview: String {
        // Strip HTML tags for preview
        let stripped = article.content
            .replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
            .replacingOccurrences(of: "&nbsp;", with: " ")
            .replacingOccurrences(of: "&amp;", with: "&")
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)

        if stripped.count > 200 {
            return String(stripped.prefix(200)) + "..."
        }
        return stripped
    }
}

struct HTMLContentView: View {
    let htmlContent: String
    var useSerifFont: Bool = false

    var body: some View {
        Text(attributedString)
            .font(useSerifFont ? .custom("Georgia", size: 17) : .body)
    }

    private var attributedString: AttributedString {
        // Convert HTML to AttributedString
        let htmlData = Data(htmlContent.utf8)

        if let nsAttributedString = try? NSAttributedString(
            data: htmlData,
            options: [
                .documentType: NSAttributedString.DocumentType.html,
                .characterEncoding: String.Encoding.utf8.rawValue
            ],
            documentAttributes: nil
        ) {
            // Convert to AttributedString and apply appropriate font
            var attributedString = AttributedString(nsAttributedString)

            // Reset font while preserving bold/italic
            for run in attributedString.runs {
                let range = run.range
                if useSerifFont {
                    attributedString[range].font = .custom("Georgia", size: 17)
                } else {
                    attributedString[range].font = .body
                }
            }

            return attributedString
        }

        // Fallback to plain text if HTML parsing fails
        return AttributedString(htmlContent)
    }
}

#Preview {
    NavigationStack {
        DigestDetailView(
            digest: Digest(
                generatedAt: Date(),
                epubFilePath: "/path/to/file.epub",
                articleCount: 5,
                briefingCount: 3,
                deepDiveCount: 2,
                triggerType: .manual
            )
        )
    }
}
