"""PDF generation service using WeasyPrint."""

from __future__ import annotations

import base64
import logging
import os
import re
from datetime import datetime
from html import escape as html_escape

from app.core.config import Settings, get_settings
from app.services.content_processor import ExtractedArticle
from app.services.cover_image_service import CoverImage
from app.services.digest_content_formatter import format_digest_content_to_html

logger = logging.getLogger(__name__)


class PdfGenerator:
    """Generate digest PDFs with feed-grouped sections and article content."""

    CSS_STYLES = """
    @page {
        size: A4;
        margin: 16mm;
    }

    body {
        font-family: Georgia, serif;
        font-size: 11pt;
        line-height: 1.45;
        color: #111;
    }

    .cover {
        page-break-after: always;
        text-align: center;
        padding-top: 20mm;
    }

    .cover h1 {
        margin: 0 0 8mm 0;
        font-size: 34pt;
    }

    .cover .meta {
        color: #444;
        font-size: 12pt;
        margin: 2mm 0;
    }

    .cover img {
        display: block;
        max-width: 150mm;
        max-height: 120mm;
        width: auto;
        height: auto;
        margin: 0 auto 10mm auto;
    }

    .toc {
        page-break-after: always;
    }

    .toc h2 {
        margin: 0 0 6mm 0;
        font-size: 18pt;
    }

    .toc ul {
        margin: 0;
        padding-left: 7mm;
    }

    .feed-section {
        page-break-before: always;
        border-bottom: 1px solid #ccc;
        margin-bottom: 8mm;
        padding-bottom: 2mm;
    }

    .feed-section h2 {
        margin: 0;
        font-size: 18pt;
    }

    .article {
        margin-bottom: 10mm;
        page-break-inside: avoid;
    }

    .article h3 {
        margin: 0 0 2mm 0;
        font-size: 14pt;
    }

    .article .meta {
        color: #555;
        font-size: 9pt;
        margin-bottom: 3mm;
    }

    .article .mode {
        background: #efefef;
        border-radius: 3px;
        display: inline-block;
        margin-left: 4px;
        padding: 1px 6px;
        font-size: 8pt;
    }

    .article .content p {
        margin: 0 0 3mm 0;
        text-align: justify;
    }

    .article .content pre {
        background: #f6f6f6;
        border-radius: 4px;
        overflow-x: auto;
        padding: 3mm;
        font-size: 9pt;
    }

    .article .content code {
        font-family: "Menlo", "Consolas", monospace;
        font-size: 0.92em;
    }
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def generate(
        self,
        articles: list[ExtractedArticle],
        period: str,
        date: datetime | None = None,
        saved_articles: list[ExtractedArticle] | None = None,
        newsletter_articles: list[ExtractedArticle] | None = None,
        media_articles: list[ExtractedArticle] | None = None,
        cover_image: CoverImage | None = None,
        page_size: str = "A4",
    ) -> str:
        """Generate a PDF digest and return the output path."""
        if date is None:
            date = datetime.utcnow()

        all_articles: list[ExtractedArticle] = list(articles)
        if saved_articles:
            all_articles.extend(saved_articles)
        if newsletter_articles:
            all_articles.extend(newsletter_articles)
        if media_articles:
            all_articles.extend(media_articles)

        filename = f"{date.strftime('%Y-%m-%d')}_{period}.pdf"
        output_path = os.path.join(self.settings.output_dir, filename)
        os.makedirs(self.settings.output_dir, exist_ok=True)

        html_doc = self._build_html(
            all_articles=all_articles,
            period=period,
            date=date,
            page_size=page_size,
            cover_image=cover_image,
        )

        # WeasyPrint import is kept local so app startup errors are clearer
        # when PDF dependencies are not installed.
        from weasyprint import HTML

        HTML(string=html_doc).write_pdf(output_path)
        logger.info("Generated PDF: %s with %s articles", output_path, len(all_articles))
        return output_path

    def _build_html(
        self,
        *,
        all_articles: list[ExtractedArticle],
        period: str,
        date: datetime,
        page_size: str,
        cover_image: CoverImage | None,
    ) -> str:
        page_size_css = self._normalized_page_size(page_size)
        css = self.CSS_STYLES.replace("size: A4;", f"size: {page_size_css};")

        toc_items: list[str] = []
        section_blocks: list[str] = []

        article_groups = self._grouped_sections(all_articles)
        for section_title, grouped_articles in article_groups:
            toc_items.append(f"<li>{html_escape(section_title)}</li>")
            article_html = "\n".join(self._render_article(article) for article in grouped_articles)
            section_blocks.append(
                f"""
                <section class="feed-section">
                    <h2>{html_escape(section_title)}</h2>
                </section>
                {article_html}
                """
            )

        cover_html = self._render_cover(date, period, len(all_articles), cover_image)
        toc_html = (
            f"""
            <section class="toc">
                <h2>Table of Contents</h2>
                <ul>
                    {''.join(toc_items)}
                </ul>
            </section>
            """
            if toc_items
            else ""
        )

        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Epilogue Digest {date.strftime('%Y-%m-%d')} ({html_escape(period)})</title>
  <style>{css}</style>
</head>
<body>
  {cover_html}
  {toc_html}
  {''.join(section_blocks)}
</body>
</html>"""

    @staticmethod
    def _normalized_page_size(page_size: str) -> str:
        normalized = page_size.strip().upper()
        if normalized in {"A4", "LETTER", "A5"}:
            return normalized
        return "A4"

    def _render_cover(
        self,
        date: datetime,
        period: str,
        article_count: int,
        cover_image: CoverImage | None,
    ) -> str:
        image_html = ""
        if cover_image:
            mime = cover_image.media_type.split(";")[0].strip().lower() or "image/png"
            encoded = base64.b64encode(cover_image.data).decode("ascii")
            image_html = f'<img src="data:{mime};base64,{encoded}" alt="Digest cover"/>'

        return f"""
        <section class="cover">
            {image_html}
            <h1>Epilogue</h1>
            <div class="meta">{html_escape(date.strftime('%A, %B %d, %Y'))}</div>
            <div class="meta">{html_escape(period.capitalize())} Edition</div>
            <div class="meta">{article_count} articles</div>
        </section>
        """

    @staticmethod
    def _group_articles_by_feed(
        articles: list[ExtractedArticle],
    ) -> list[tuple[str, list[ExtractedArticle]]]:
        grouped: dict[str, list[ExtractedArticle]] = {}
        for article in articles:
            title = article.feed_title.strip() or "Unknown Feed"
            grouped.setdefault(title, []).append(article)
        return list(grouped.items())

    def _grouped_sections(
        self,
        articles: list[ExtractedArticle],
    ) -> list[tuple[str, list[ExtractedArticle]]]:
        regular_articles = [a for a in articles if a.content_type == "article"]
        media_articles = [a for a in articles if a.content_type != "article"]

        sections: list[tuple[str, list[ExtractedArticle]]] = []
        sections.extend(self._group_articles_by_feed(regular_articles))

        section_labels = {"podcast": "Podcasts", "youtube": "YouTube"}
        media_by_type: dict[str, list[ExtractedArticle]] = {}
        for article in media_articles:
            media_by_type.setdefault(article.content_type, []).append(article)

        for content_type, type_articles in media_by_type.items():
            section_title = section_labels.get(content_type, content_type.capitalize())
            for feed_title, feed_articles in self._group_articles_by_feed(type_articles):
                sections.append((f"{section_title}: {feed_title}", feed_articles))

        return sections

    def _render_article(self, article: ExtractedArticle) -> str:
        source = html_escape(article.url)
        author = html_escape(article.author) if article.author else "Unknown author"
        content_html = format_digest_content_to_html(article.content)
        mode = "Summary" if article.is_summary else "Full text"

        return f"""
        <article class="article">
            <h3>{html_escape(article.title)}</h3>
            <div class="meta">
                {author} | <a href="{source}">{source}</a>
                <span class="mode">{mode}</span>
            </div>
            <div class="content">
                {content_html}
            </div>
        </article>
        """

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "feed"
