//
//  EinkReaderView.swift
//  Epilogue
//
//  E-ink optimized paginated reader for digest content.
//  No animations, tap/swipe navigation, serif typography.
//  Text is split across pages using CoreText measurement.
//

import SwiftUI
import CoreText
import Domain

// MARK: - Page Model

private enum PageItem: Identifiable {
    case sectionHeader(title: String, subtitle: String)
    case articlePage(article: DigestArticle, attributedText: NSAttributedString, pageIndex: Int, totalArticlePages: Int)

    var id: String {
        switch self {
        case .sectionHeader(let title, _):
            return "header-\(title)"
        case .articlePage(let article, _, let pageIndex, _):
            return "\(article.id.uuidString)-p\(pageIndex)"
        }
    }

    var articleId: UUID? {
        switch self {
        case .articlePage(let article, _, _, _): return article.id
        default: return nil
        }
    }
}

// MARK: - Text Paginator

private struct TextPaginator {
    /// Splits an NSAttributedString into page-sized chunks using CoreText.
    static func paginate(
        attributedString: NSAttributedString,
        size: CGSize
    ) -> [NSAttributedString] {
        guard attributedString.length > 0, size.width > 0, size.height > 0 else {
            return [attributedString]
        }

        var pages: [NSAttributedString] = []
        let framesetter = CTFramesetterCreateWithAttributedString(attributedString)
        var currentIndex = 0
        let totalLength = attributedString.length

        while currentIndex < totalLength {
            let path = CGPath(rect: CGRect(origin: .zero, size: size), transform: nil)
            let frame = CTFramesetterCreateFrame(
                framesetter,
                CFRangeMake(currentIndex, 0),
                path,
                nil
            )

            let visibleRange = CTFrameGetVisibleStringRange(frame)
            if visibleRange.length == 0 {
                // Safety: avoid infinite loop if nothing fits
                break
            }

            let pageText = attributedString.attributedSubstring(
                from: NSRange(location: visibleRange.location, length: visibleRange.length)
            )
            pages.append(pageText)
            currentIndex += visibleRange.length
        }

        return pages.isEmpty ? [attributedString] : pages
    }

    /// Builds a styled NSAttributedString for an article's header (title, author, source).
    static func buildArticleHeader(article: DigestArticle) -> NSAttributedString {
        let result = NSMutableAttributedString()

        // Title
        let titleFont = UIFont(name: "Georgia-Bold", size: 22) ?? UIFont.boldSystemFont(ofSize: 22)
        result.append(NSAttributedString(
            string: article.title + "\n",
            attributes: [
                .font: titleFont,
                .foregroundColor: UIColor.label
            ]
        ))

        // Author
        if !article.author.isEmpty {
            let authorFont = UIFont(name: "Georgia-Italic", size: 14) ?? UIFont.italicSystemFont(ofSize: 14)
            result.append(NSAttributedString(
                string: "By \(article.author)\n",
                attributes: [
                    .font: authorFont,
                    .foregroundColor: UIColor.secondaryLabel
                ]
            ))
        }

        // Feed name
        let feedFont = UIFont(name: "Georgia", size: 12) ?? UIFont.systemFont(ofSize: 12)
        result.append(NSAttributedString(
            string: article.feedName + "\n\n",
            attributes: [
                .font: feedFont,
                .foregroundColor: UIColor.secondaryLabel
            ]
        ))

        return result
    }

    /// Builds a styled NSAttributedString for the article body from HTML content.
    static func buildArticleBody(html: String) -> NSAttributedString {
        let bodyFont = UIFont(name: "Georgia", size: 17) ?? UIFont.systemFont(ofSize: 17)
        let style = NSMutableParagraphStyle()
        style.lineSpacing = 8

        // If content looks like plain text (no HTML tags), convert newlines to <br> tags
        let containsHtmlTags = html.range(of: "<[a-zA-Z][^>]*>", options: .regularExpression) != nil
        let htmlContent: String
        if containsHtmlTags {
            htmlContent = html
        } else {
            // Plain text: wrap in basic HTML to preserve line breaks
            let escaped = html
                .replacingOccurrences(of: "&", with: "&amp;")
                .replacingOccurrences(of: "<", with: "&lt;")
                .replacingOccurrences(of: ">", with: "&gt;")
            htmlContent = "<p>" + escaped
                .components(separatedBy: "\n\n")
                .joined(separator: "</p><p>")
                .replacingOccurrences(of: "\n", with: "<br>") + "</p>"
        }

        // Try HTML parsing
        if let htmlData = htmlContent.data(using: .utf8),
           let parsed = try? NSMutableAttributedString(
            data: htmlData,
            options: [
                .documentType: NSAttributedString.DocumentType.html,
                .characterEncoding: String.Encoding.utf8.rawValue
            ],
            documentAttributes: nil
           ) {
            // Apply serif font and line spacing throughout
            let range = NSRange(location: 0, length: parsed.length)
            parsed.enumerateAttribute(.font, in: range) { value, subRange, _ in
                if let existingFont = value as? UIFont {
                    var traits = existingFont.fontDescriptor.symbolicTraits
                    var newFont = bodyFont
                    if traits.contains(.traitBold) {
                        newFont = UIFont(name: "Georgia-Bold", size: 17) ?? bodyFont
                    }
                    if traits.contains(.traitItalic) {
                        newFont = UIFont(name: "Georgia-Italic", size: 17) ?? bodyFont
                    }
                    if traits.contains(.traitBold) && traits.contains(.traitItalic) {
                        newFont = UIFont(name: "Georgia-BoldItalic", size: 17) ?? bodyFont
                    }
                    parsed.addAttribute(.font, value: newFont, range: subRange)
                } else {
                    parsed.addAttribute(.font, value: bodyFont, range: subRange)
                }
            }
            parsed.addAttribute(.paragraphStyle, value: style, range: range)
            parsed.addAttribute(.foregroundColor, value: UIColor.label, range: range)
            return parsed
        }

        // Fallback: plain text
        return NSAttributedString(
            string: html.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression),
            attributes: [
                .font: bodyFont,
                .paragraphStyle: style,
                .foregroundColor: UIColor.label
            ]
        )
    }

    /// Combines header + body into one attributed string for an article.
    static func buildFullArticle(article: DigestArticle) -> NSAttributedString {
        let result = NSMutableAttributedString()
        result.append(buildArticleHeader(article: article))
        result.append(buildArticleBody(html: article.content))
        return result
    }
}

// MARK: - EinkReaderView

struct EinkReaderView: View {
    let articles: [DigestArticle]
    let briefingCount: Int
    var epubFilePath: String? = nil

    @Environment(\.dismiss) private var dismiss
    @State private var currentPage = 0
    @State private var showNavigationBar = true
    @State private var showTableOfContents = false
    @State private var viewportSize: CGSize = .zero
    @State private var paginatedPages: [PageItem] = []
    @State private var articleFirstPageIndex: [UUID: Int] = [:]

    private var totalPages: Int { max(paginatedPages.count, 1) }

    var body: some View {
        VStack(spacing: 0) {
            // Main content area
            GeometryReader { geometry in
                ZStack {
                    // Page content
                    if !paginatedPages.isEmpty, currentPage < paginatedPages.count {
                        pageView(for: paginatedPages[currentPage])
                    } else {
                        emptyView
                    }

                    // Invisible tap zones
                    HStack(spacing: 0) {
                        Color.clear
                            .contentShape(Rectangle())
                            .onTapGesture { goToPreviousPage() }
                        Color.clear
                            .contentShape(Rectangle())
                            .onTapGesture { showNavigationBar.toggle() }
                        Color.clear
                            .contentShape(Rectangle())
                            .onTapGesture { goToNextPage() }
                    }
                }
                .gesture(
                    DragGesture(minimumDistance: 50)
                        .onEnded { value in
                            let threshold = geometry.size.width * 0.15
                            if value.translation.width > threshold {
                                goToPreviousPage()
                            } else if value.translation.width < -threshold {
                                goToNextPage()
                            }
                        }
                )
                .onChange(of: geometry.size) { _, newSize in
                    if newSize != viewportSize {
                        viewportSize = newSize
                        rebuildPages()
                    }
                }
                .onAppear {
                    viewportSize = geometry.size
                    rebuildPages()
                }
            }

            // Navigation bar
            if showNavigationBar {
                navigationBar
            }
        }
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button {
                    dismiss()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "chevron.left")
                        Text("Back")
                    }
                }
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                if epubFilePath != nil {
                    ShareLink(item: URL(fileURLWithPath: epubFilePath!)) {
                        Image(systemName: "square.and.arrow.up")
                    }
                }
            }
        }
        .sheet(isPresented: $showTableOfContents) {
            tableOfContents
        }
    }

    // MARK: - Pagination

    private func rebuildPages() {
        guard viewportSize.width > 0, viewportSize.height > 0 else { return }

        let padding: CGFloat = 32 // 16pt on each side
        let textSize = CGSize(
            width: viewportSize.width - padding,
            height: viewportSize.height - padding
        )

        var result: [PageItem] = []
        var firstPageMap: [UUID: Int] = [:]

        let briefings = Array(articles.prefix(briefingCount))
        let deepDives = Array(articles.dropFirst(briefingCount))

        if !briefings.isEmpty {
            result.append(.sectionHeader(title: "The Briefing", subtitle: "AI-generated summaries"))

            for article in briefings {
                firstPageMap[article.id] = result.count
                let fullText = TextPaginator.buildFullArticle(article: article)
                let articlePages = TextPaginator.paginate(attributedString: fullText, size: textSize)
                for (i, pageText) in articlePages.enumerated() {
                    result.append(.articlePage(
                        article: article,
                        attributedText: pageText,
                        pageIndex: i,
                        totalArticlePages: articlePages.count
                    ))
                }
            }
        }

        if !deepDives.isEmpty {
            result.append(.sectionHeader(title: "Deep Dives", subtitle: "Full articles for in-depth reading"))

            for article in deepDives {
                firstPageMap[article.id] = result.count
                let fullText = TextPaginator.buildFullArticle(article: article)
                let articlePages = TextPaginator.paginate(attributedString: fullText, size: textSize)
                for (i, pageText) in articlePages.enumerated() {
                    result.append(.articlePage(
                        article: article,
                        attributedText: pageText,
                        pageIndex: i,
                        totalArticlePages: articlePages.count
                    ))
                }
            }
        }

        paginatedPages = result
        articleFirstPageIndex = firstPageMap

        // Keep current page in bounds
        if currentPage >= result.count {
            currentPage = max(result.count - 1, 0)
        }
    }

    // MARK: - Page Views

    @ViewBuilder
    private func pageView(for item: PageItem) -> some View {
        switch item {
        case .sectionHeader(let title, let subtitle):
            sectionHeaderPage(title: title, subtitle: subtitle)
        case .articlePage(_, let attributedText, let pageIndex, let totalArticlePages):
            articlePageView(
                attributedText: attributedText,
                pageIndex: pageIndex,
                totalArticlePages: totalArticlePages
            )
        }
    }

    private func sectionHeaderPage(title: String, subtitle: String) -> some View {
        VStack(spacing: 12) {
            Spacer()
            Text(title)
                .font(.custom("Georgia", size: 28))
                .fontWeight(.bold)
            Text(subtitle)
                .font(.custom("Georgia", size: 16))
                .foregroundStyle(.secondary)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private func articlePageView(
        attributedText: NSAttributedString,
        pageIndex: Int,
        totalArticlePages: Int
    ) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            // Render the attributed text
            AttributedTextView(attributedString: attributedText)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

            // Page indicator for multi-page articles
            if totalArticlePages > 1 {
                Text("Page \(pageIndex + 1) of \(totalArticlePages)")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
        }
        .padding(16)
    }

    private var emptyView: some View {
        VStack {
            Spacer()
            Text("No articles in this digest")
                .font(.custom("Georgia", size: 17))
                .foregroundStyle(.secondary)
            Spacer()
        }
    }

    // MARK: - Navigation Bar

    private var navigationBar: some View {
        VStack(spacing: 0) {
            Divider()

            HStack {
                Button {
                    goToPreviousPage()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "chevron.left")
                        Text("Prev")
                    }
                }
                .disabled(currentPage <= 0)

                Spacer()

                Button("Contents") {
                    showTableOfContents = true
                }

                Spacer()

                Text("\(currentPage + 1) / \(totalPages)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(minWidth: 50)

                Spacer()

                Button {
                    goToNextPage()
                } label: {
                    HStack(spacing: 4) {
                        Text("Next")
                        Image(systemName: "chevron.right")
                    }
                }
                .disabled(currentPage >= totalPages - 1)
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
        .background(Color(.systemBackground))
    }

    // MARK: - Table of Contents

    private var tableOfContents: some View {
        NavigationStack {
            List {
                ForEach(Array(articles.enumerated()), id: \.element.id) { index, article in
                    Button {
                        if let pageIdx = articleFirstPageIndex[article.id] {
                            currentPage = pageIdx
                        }
                        showTableOfContents = false
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(article.title)
                                    .font(.headline)
                                    .foregroundStyle(.primary)
                                HStack {
                                    Text(article.feedName)
                                    if index < briefingCount {
                                        Text("• Briefing")
                                    }
                                }
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            }
                            Spacer()
                            if let firstPage = articleFirstPageIndex[article.id],
                               let currentArticleId = paginatedPages[safe: currentPage]?.articleId,
                               currentArticleId == article.id {
                                Text("Reading")
                                    .font(.caption2)
                                    .foregroundStyle(.blue)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Contents")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { showTableOfContents = false }
                }
            }
        }
    }

    // MARK: - Navigation

    private func goToNextPage() {
        if currentPage < totalPages - 1 {
            currentPage += 1
        }
    }

    private func goToPreviousPage() {
        if currentPage > 0 {
            currentPage -= 1
        }
    }
}

// MARK: - UIKit Text Rendering

/// UIViewRepresentable that renders an NSAttributedString without scrolling.
private struct AttributedTextView: UIViewRepresentable {
    let attributedString: NSAttributedString

    func makeUIView(context: Context) -> UILabel {
        let label = UILabel()
        label.numberOfLines = 0
        label.lineBreakMode = .byWordWrapping
        label.setContentHuggingPriority(.required, for: .vertical)
        label.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        label.preferredMaxLayoutWidth = UIScreen.main.bounds.width - 32
        return label
    }

    func updateUIView(_ label: UILabel, context: Context) {
        label.attributedText = attributedString
        label.preferredMaxLayoutWidth = label.bounds.width > 0 ? label.bounds.width : UIScreen.main.bounds.width - 32
    }
}

// MARK: - Collection Extension

private extension Collection {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
