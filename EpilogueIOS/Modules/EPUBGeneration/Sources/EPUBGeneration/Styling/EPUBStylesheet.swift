//
//  EPUBStylesheet.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// E-ink optimized CSS stylesheet for EPUB files
public enum EPUBStylesheet {
    public static let einkOptimizedCSS = """
    /* E-ink Optimized Stylesheet for Epilogue */

    /* Reset and base styles */
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }

    body {
        font-family: "Merriweather", "Georgia", serif;
        font-size: 1.1em;
        line-height: 1.6;
        color: #000000;
        background-color: #FFFFFF;
        padding: 1em;
        max-width: 40em;
        margin: 0 auto;
    }

    /* Cover page */
    .cover {
        text-align: center;
        padding: 4em 0;
        min-height: 80vh;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    .cover h1 {
        font-size: 3em;
        font-weight: bold;
        margin-bottom: 0.5em;
        letter-spacing: 0.05em;
    }

    .cover h2 {
        font-size: 1.5em;
        font-weight: normal;
        margin-bottom: 2em;
    }

    .cover .date {
        font-size: 1.2em;
        margin-top: 2em;
    }

    /* Section titles */
    .section-title {
        font-size: 2em;
        font-weight: bold;
        margin: 2em 0 1em 0;
        padding-bottom: 0.5em;
        border-bottom: 3px solid #000000;
        page-break-before: always;
    }

    /* Article titles */
    .article-title {
        font-size: 1.5em;
        font-weight: bold;
        margin: 1.5em 0 0.5em 0;
        line-height: 1.3;
    }

    /* Author */
    .author {
        font-style: italic;
        margin-bottom: 1em;
        color: #000000;
    }

    /* Article content */
    .article-content {
        margin: 1.5em 0;
    }

    .article-content p {
        margin-bottom: 1em;
        text-align: justify;
    }

    .article-content h1,
    .article-content h2,
    .article-content h3 {
        font-weight: bold;
        margin: 1.5em 0 0.5em 0;
        line-height: 1.3;
    }

    .article-content h1 {
        font-size: 1.4em;
    }

    .article-content h2 {
        font-size: 1.2em;
    }

    .article-content h3 {
        font-size: 1.1em;
    }

    .article-content ul,
    .article-content ol {
        margin: 1em 0 1em 2em;
    }

    .article-content li {
        margin-bottom: 0.5em;
    }

    .article-content blockquote {
        margin: 1em 0;
        padding-left: 1.5em;
        border-left: 3px solid #000000;
        font-style: italic;
    }

    .article-content code {
        font-family: "Courier New", monospace;
        background-color: #F0F0F0;
        padding: 0.2em 0.4em;
        border-radius: 3px;
    }

    .article-content pre {
        font-family: "Courier New", monospace;
        background-color: #F0F0F0;
        padding: 1em;
        margin: 1em 0;
        overflow-x: auto;
        border: 1px solid #000000;
    }

    /* Source link */
    .source {
        margin-top: 2em;
        padding-top: 1em;
        border-top: 1px solid #000000;
        font-size: 0.9em;
    }

    .source a {
        color: #000000;
        text-decoration: underline;
    }

    /* Links */
    a {
        color: #000000;
        text-decoration: underline;
    }

    /* Strong emphasis */
    strong, b {
        font-weight: bold;
    }

    em, i {
        font-style: italic;
    }

    /* Page breaks */
    .page-break {
        page-break-after: always;
    }

    /* Prevent orphans and widows */
    p {
        orphans: 3;
        widows: 3;
    }

    /* High contrast for e-ink */
    img {
        max-width: 100%;
        height: auto;
        border: 1px solid #000000;
        margin: 1em 0;
    }

    /* Tables */
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 1em 0;
    }

    th, td {
        border: 1px solid #000000;
        padding: 0.5em;
        text-align: left;
    }

    th {
        font-weight: bold;
        background-color: #F0F0F0;
    }

    /* Horizontal rule */
    hr {
        border: none;
        border-top: 2px solid #000000;
        margin: 2em 0;
    }
    """
}
