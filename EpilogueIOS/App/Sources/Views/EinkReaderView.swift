//
//  EinkReaderView.swift
//  Epilogue
//
//  E-ink optimized paginated reader for digest content.
//  No animations, tap/swipe navigation, serif typography.
//

import SwiftUI
import Domain

// MARK: - Page Model

private enum PageItem: Identifiable {
    case sectionHeader(title: String, subtitle: String)
    case article(DigestArticle)

    var id: String {
        switch self {
        case .sectionHeader(let title, _):
            return "header-\(title)"
        case .article(let article):
            return article.id.uuidString
        }
    }
}

// MARK: - EinkReaderView

struct EinkReaderView: View {
    let articles: [DigestArticle]
    let briefingCount: Int

    @State private var currentPage = 0
    @State private var showNavigationBar = true
    @State private var showTableOfContents = false
    @State private var viewWidth: CGFloat = 0

    private var pages: [PageItem] {
        var result: [PageItem] = []

        let briefings = Array(articles.prefix(briefingCount))
        let deepDives = Array(articles.dropFirst(briefingCount))

        if !briefings.isEmpty {
            result.append(.sectionHeader(
                title: "The Briefing",
                subtitle: "AI-generated summaries"
            ))
            briefings.forEach { result.append(.article($0)) }
        }

        if !deepDives.isEmpty {
            result.append(.sectionHeader(
                title: "Deep Dives",
                subtitle: "Full articles for in-depth reading"
            ))
            deepDives.forEach { result.append(.article($0)) }
        }

        return result
    }

    private var totalPages: Int { max(pages.count, 1) }

    var body: some View {
        VStack(spacing: 0) {
            // Main content area
            GeometryReader { geometry in
                ZStack {
                    // Page content
                    if !pages.isEmpty, currentPage < pages.count {
                        pageView(for: pages[currentPage])
                    } else {
                        emptyView
                    }

                    // Invisible tap zones
                    HStack(spacing: 0) {
                        // Left third - previous
                        Color.clear
                            .contentShape(Rectangle())
                            .onTapGesture { goToPreviousPage() }

                        // Center third - toggle nav bar
                        Color.clear
                            .contentShape(Rectangle())
                            .onTapGesture { showNavigationBar.toggle() }

                        // Right third - next
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
                .onAppear { viewWidth = geometry.size.width }
            }

            // Navigation bar
            if showNavigationBar {
                navigationBar
            }
        }
        .sheet(isPresented: $showTableOfContents) {
            tableOfContents
        }
    }

    // MARK: - Pages

    @ViewBuilder
    private func pageView(for item: PageItem) -> some View {
        switch item {
        case .sectionHeader(let title, let subtitle):
            sectionHeaderPage(title: title, subtitle: subtitle)
        case .article(let article):
            articlePage(article: article)
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

    private func articlePage(article: DigestArticle) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                // Title
                Text(article.title)
                    .font(.custom("Georgia", size: 22))
                    .fontWeight(.bold)

                // Author
                if !article.author.isEmpty {
                    Text("By \(article.author)")
                        .font(.custom("Georgia", size: 14))
                        .italic()
                        .foregroundStyle(.secondary)
                }

                // Feed name
                Text(article.feedName)
                    .font(.custom("Georgia", size: 12))
                    .foregroundStyle(.secondary)

                Divider()
                    .padding(.vertical, 4)

                // Content
                HTMLContentView(htmlContent: article.content, useSerifFont: true)
                    .lineSpacing(8)
            }
            .padding()
            .padding(.bottom, 60)
        }
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
                        currentPage = pageIndexForArticle(at: index)
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
                            if currentPage == pageIndexForArticle(at: index) {
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

    private func pageIndexForArticle(at articleIndex: Int) -> Int {
        // Account for section headers
        if articleIndex < briefingCount {
            // Briefing article: header page + article index
            return (briefingCount > 0 ? 1 : 0) + articleIndex
        } else {
            // Deep dive article: briefing header + briefings + deep dive header + offset
            let deepDiveOffset = articleIndex - briefingCount
            var page = 0
            if briefingCount > 0 { page += 1 + briefingCount } // briefing header + articles
            let hasDeepDives = articles.count > briefingCount
            if hasDeepDives { page += 1 } // deep dive header
            page += deepDiveOffset
            return page
        }
    }
}
