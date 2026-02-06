//
//  EPUBBuilder.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import ZIPFoundation
import Domain

/// Service for building EPUB files from processed articles
public final class EPUBBuilder: EPUBBuilderProtocol, @unchecked Sendable {
    private let fileManager = FileManager.default

    public init() {}

    /// Generate an EPUB file from articles
    public func generateEPUB(
        articles: [ProcessedArticle],
        outputPath: String,
        date: Date = Date()
    ) throws -> URL {
        let outputURL = URL(fileURLWithPath: outputPath)

        // Create temporary directory for EPUB contents
        let tempDir = fileManager.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)

        try fileManager.createDirectory(at: tempDir, withIntermediateDirectories: true)

        defer {
            try? fileManager.removeItem(at: tempDir)
        }

        // Generate EPUB structure
        try createEPUBStructure(in: tempDir, articles: articles, date: date)

        // Create ZIP archive (EPUB is a ZIP file)
        try createZIPArchive(from: tempDir, to: outputURL)

        return outputURL
    }

    // MARK: - Private Helpers

    private func createEPUBStructure(
        in directory: URL,
        articles: [ProcessedArticle],
        date: Date
    ) throws {
        // Create required directories
        let metaInfDir = directory.appendingPathComponent("META-INF")
        let oebpsDir = directory.appendingPathComponent("OEBPS")
        try fileManager.createDirectory(at: metaInfDir, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: oebpsDir, withIntermediateDirectories: true)

        // Create mimetype file (must be first and uncompressed)
        try createMimetype(in: directory)

        // Create container.xml
        try createContainerXML(in: metaInfDir)

        // Create content.opf
        try createContentOPF(in: oebpsDir, articles: articles, date: date)

        // Create toc.ncx
        try createTOCNCX(in: oebpsDir, articles: articles)

        // Create CSS
        try createStylesheet(in: oebpsDir)

        // Create cover page
        try createCoverPage(in: oebpsDir, date: date)

        // Create article chapters
        try createChapters(in: oebpsDir, articles: articles)
    }

    private func createMimetype(in directory: URL) throws {
        let mimetypeURL = directory.appendingPathComponent("mimetype")
        let content = "application/epub+zip"
        try content.write(to: mimetypeURL, atomically: true, encoding: .utf8)
    }

    private func createContainerXML(in metaInfDir: URL) throws {
        let containerURL = metaInfDir.appendingPathComponent("container.xml")
        let xml = """
        <?xml version="1.0" encoding="UTF-8"?>
        <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
            <rootfiles>
                <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
            </rootfiles>
        </container>
        """
        try xml.write(to: containerURL, atomically: true, encoding: .utf8)
    }

    private func createContentOPF(
        in oebpsDir: URL,
        articles: [ProcessedArticle],
        date: Date
    ) throws {
        let contentURL = oebpsDir.appendingPathComponent("content.opf")
        let dateFormatter = ISO8601DateFormatter()
        let dateString = dateFormatter.string(from: date)
        let feedGroups = groupArticlesByFeed(articles: articles)

        var manifest = """
            <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
            <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
            <item id="css" href="stylesheet.css" media-type="text/css"/>
        """

        var spine = "<itemref idref=\"cover\"/>"

        for (feedIndex, (_, feedArticles)) in feedGroups.enumerated() {
            manifest += "\n    <item id=\"feedSection\(feedIndex)\" href=\"feed\(feedIndex).xhtml\" media-type=\"application/xhtml+xml\"/>"
            spine += "\n    <itemref idref=\"feedSection\(feedIndex)\"/>"

            for articleIndex in feedArticles.indices {
                manifest += "\n    <item id=\"feed\(feedIndex)Article\(articleIndex)\" href=\"feed\(feedIndex)_article\(articleIndex).xhtml\" media-type=\"application/xhtml+xml\"/>"
                spine += "\n    <itemref idref=\"feed\(feedIndex)Article\(articleIndex)\"/>"
            }
        }

        let xml = """
        <?xml version="1.0" encoding="UTF-8"?>
        <package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
            <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
                <dc:identifier id="uid">epilogue-\(UUID().uuidString)</dc:identifier>
                <dc:title>Epilogue Daily Digest</dc:title>
                <dc:creator>Epilogue</dc:creator>
                <dc:language>en</dc:language>
                <dc:date>\(dateString)</dc:date>
                <meta property="dcterms:modified">\(dateString)</meta>
            </metadata>
            <manifest>
        \(manifest)
            </manifest>
            <spine toc="ncx">
        \(spine)
            </spine>
        </package>
        """
        try xml.write(to: contentURL, atomically: true, encoding: .utf8)
    }

    private func createTOCNCX(in oebpsDir: URL, articles: [ProcessedArticle]) throws {
        let tocURL = oebpsDir.appendingPathComponent("toc.ncx")
        let feedGroups = groupArticlesByFeed(articles: articles)

        var navPoints = """
            <navPoint id="cover" playOrder="1">
                <navLabel><text>Cover</text></navLabel>
                <content src="cover.xhtml"/>
            </navPoint>
        """

        var playOrder = 2

        for (feedIndex, (feedName, feedArticles)) in feedGroups.enumerated() {
            let feedPlayOrder = playOrder
            playOrder += 1

            var feedChildren = ""
            for (articleIndex, article) in feedArticles.enumerated() {
                let articlePlayOrder = playOrder
                playOrder += 1
                feedChildren += """
                
                    <navPoint id="feed\(feedIndex)-article\(articleIndex)" playOrder="\(articlePlayOrder)">
                        <navLabel><text>\(escapeXML(article.title))</text></navLabel>
                        <content src="feed\(feedIndex)_article\(articleIndex).xhtml"/>
                    </navPoint>
                """
            }

            navPoints += """
            \n    <navPoint id="feed\(feedIndex)" playOrder="\(feedPlayOrder)">
                <navLabel><text>\(escapeXML(feedName))</text></navLabel>
                <content src="feed\(feedIndex).xhtml"/>\(feedChildren)
            </navPoint>
            """
        }

        let xml = """
        <?xml version="1.0" encoding="UTF-8"?>
        <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
            <head>
                <meta name="dtb:uid" content="epilogue-digest"/>
            </head>
            <docTitle><text>Epilogue Daily Digest</text></docTitle>
            <navMap>
        \(navPoints)
            </navMap>
        </ncx>
        """
        try xml.write(to: tocURL, atomically: true, encoding: .utf8)
    }

    private func createStylesheet(in oebpsDir: URL) throws {
        let cssURL = oebpsDir.appendingPathComponent("stylesheet.css")
        let css = EPUBStylesheet.einkOptimizedCSS
        try css.write(to: cssURL, atomically: true, encoding: .utf8)
    }

    private func createCoverPage(in oebpsDir: URL, date: Date) throws {
        let coverURL = oebpsDir.appendingPathComponent("cover.xhtml")
        let dateFormatter = DateFormatter()
        dateFormatter.dateStyle = .long
        let dateString = dateFormatter.string(from: date)

        let xhtml = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head>
            <title>Epilogue Daily Digest</title>
            <link rel="stylesheet" type="text/css" href="stylesheet.css"/>
        </head>
        <body>
            <div class="cover">
                <h1>Epilogue</h1>
                <h2>Daily Digest</h2>
                <p class="date">\(dateString)</p>
            </div>
        </body>
        </html>
        """
        try xhtml.write(to: coverURL, atomically: true, encoding: .utf8)
    }

    private func createChapters(in oebpsDir: URL, articles: [ProcessedArticle]) throws {
        let feedGroups = groupArticlesByFeed(articles: articles)

        for (feedIndex, (feedName, feedArticles)) in feedGroups.enumerated() {
            try createFeedSectionChapter(
                in: oebpsDir,
                feedName: feedName,
                articleCount: feedArticles.count,
                filename: "feed\(feedIndex).xhtml"
            )

            for (articleIndex, article) in feedArticles.enumerated() {
                try createChapter(
                    in: oebpsDir,
                    article: article,
                    filename: "feed\(feedIndex)_article\(articleIndex).xhtml"
                )
            }
        }
    }

    private func createFeedSectionChapter(
        in oebpsDir: URL,
        feedName: String,
        articleCount: Int,
        filename: String
    ) throws {
        let chapterURL = oebpsDir.appendingPathComponent(filename)
        let articleLabel = articleCount == 1 ? "article" : "articles"

        let xhtml = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head>
            <title>\(feedName)</title>
            <link rel="stylesheet" type="text/css" href="stylesheet.css"/>
        </head>
        <body>
            <h1 class="section-title">\(feedName)</h1>
            <p class="section-intro">\(articleCount) \(articleLabel)</p>
        </body>
        </html>
        """
        try xhtml.write(to: chapterURL, atomically: true, encoding: .utf8)
    }

    private func createChapter(
        in oebpsDir: URL,
        article: ProcessedArticle,
        filename: String
    ) throws {
        let chapterURL = oebpsDir.appendingPathComponent(filename)

        let authorHTML = article.author.isEmpty ? "" : "<p class=\"author\">By \(article.author)</p>\n    "

        let xhtml = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head>
            <title>\(article.title)</title>
            <link rel="stylesheet" type="text/css" href="stylesheet.css"/>
        </head>
        <body>
            <h2 class="article-title">\(article.title)</h2>
            \(authorHTML)<div class="article-content">
        \(article.content)
            </div>
            <p class="source"><a href="\(article.originalUrl)">Read original</a></p>
        </body>
        </html>
        """
        try xhtml.write(to: chapterURL, atomically: true, encoding: .utf8)
    }

    private func groupArticlesByFeed(articles: [ProcessedArticle]) -> [(String, [ProcessedArticle])] {
        var grouped: [(String, [ProcessedArticle])] = []

        for article in articles {
            let feedName = article.feedName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? "Unknown Feed"
                : article.feedName

            if let index = grouped.firstIndex(where: { $0.0 == feedName }) {
                grouped[index].1.append(article)
            } else {
                grouped.append((feedName, [article]))
            }
        }

        return grouped
    }

    private func escapeXML(_ text: String) -> String {
        text
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
            .replacingOccurrences(of: "'", with: "&apos;")
    }

    private func createZIPArchive(from source: URL, to destination: URL) throws {
        // Remove existing file if present
        if fileManager.fileExists(atPath: destination.path) {
            try fileManager.removeItem(at: destination)
        }

        // Create parent directory if needed
        let parentDir = destination.deletingLastPathComponent()
        if !fileManager.fileExists(atPath: parentDir.path) {
            try fileManager.createDirectory(at: parentDir, withIntermediateDirectories: true)
        }

        // Create ZIP archive
        try fileManager.zipItem(at: source, to: destination)
    }
}
