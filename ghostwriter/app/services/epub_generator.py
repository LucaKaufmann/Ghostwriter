"""EPUB generation service using EbookLib."""

import logging
import os
import re
from datetime import datetime
from uuid import uuid4

from ebooklib import epub

from app.core.config import Settings, get_settings
from app.services.content_processor import ExtractedArticle

logger = logging.getLogger(__name__)


class EpubGenerator:
    """
    EPUB file generation service.

    Creates well-formatted EPUB files with cover, TOC, and chapters.
    """

    CSS_STYLES = """
    body {
        font-family: Georgia, serif;
        line-height: 1.6;
        margin: 1em;
        color: #000;
        background: #fff;
    }
    h1 {
        font-size: 1.8em;
        margin-bottom: 0.5em;
        border-bottom: 1px solid #ccc;
        padding-bottom: 0.3em;
    }
    h2 {
        font-size: 1.4em;
        margin-top: 1.5em;
        margin-bottom: 0.5em;
    }
    .article {
        margin-bottom: 2em;
        page-break-after: always;
    }
    .article-meta {
        font-size: 0.9em;
        color: #666;
        margin-bottom: 1em;
    }
    .article-content {
        text-align: justify;
    }
    .summary-badge {
        display: inline-block;
        background: #e0e0e0;
        padding: 2px 8px;
        border-radius: 3px;
        font-size: 0.8em;
        margin-left: 0.5em;
    }
    .cover {
        text-align: center;
        padding: 2em;
    }
    .cover h1 {
        font-size: 2.5em;
        border: none;
    }
    .cover .date {
        font-size: 1.5em;
        color: #666;
    }
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """
        Initialize the EPUB generator.

        Args:
            settings: Application settings. Uses default if not provided.
        """
        self.settings = settings or get_settings()

    def generate(
        self,
        articles: list[ExtractedArticle],
        period: str,
        date: datetime | None = None,
        saved_articles: list[ExtractedArticle] | None = None,
        newsletter_articles: list[ExtractedArticle] | None = None,
    ) -> str:
        """
        Generate an EPUB file from extracted articles.

        Args:
            articles: List of ExtractedArticle objects.
            period: Time period (morning, noon, evening, manual).
            date: Date for the digest (defaults to now).

        Returns:
            Path to the generated EPUB file.
        """
        if date is None:
            date = datetime.utcnow()

        # Create EPUB book
        book = epub.EpubBook()
        book.set_identifier(str(uuid4()))
        book.set_title(f"Epilogue Digest - {date.strftime('%Y-%m-%d')} ({period})")
        book.set_language("en")
        book.add_author("Ghostwriter")

        # Add CSS
        css = epub.EpubItem(
            uid="style",
            file_name="style/main.css",
            media_type="text/css",
            content=self.CSS_STYLES.encode("utf-8"),
        )
        book.add_item(css)

        # Create cover page
        cover_content = self._create_cover(date, period, len(articles))
        cover = epub.EpubHtml(
            title="Cover",
            file_name="cover.xhtml",
            lang="en",
        )
        cover.content = cover_content.encode("utf-8")
        cover.add_item(css)
        book.add_item(cover)

        # Create chapters for each article
        chapters = []
        for i, article in enumerate(articles, 1):
            chapter = self._create_chapter(article, i, css)
            book.add_item(chapter)
            chapters.append(chapter)

        # Saved Articles section (Wallabag etc.)
        saved_chapters = []
        if saved_articles:
            divider = self._create_section_divider("Saved Articles", css)
            book.add_item(divider)
            saved_chapters.append(divider)

            offset = len(articles) + 1
            for i, article in enumerate(saved_articles, offset):
                chapter = self._create_chapter(article, i, css)
                book.add_item(chapter)
                saved_chapters.append(chapter)

        # Newsletter section
        newsletter_chapters = []
        if newsletter_articles:
            divider = self._create_section_divider(
                "Newsletters", css, file_name="section_newsletters.xhtml"
            )
            book.add_item(divider)
            newsletter_chapters.append(divider)

            for i, article in enumerate(newsletter_articles):
                chapter = self._create_newsletter_chapter(article, i, css)
                book.add_item(chapter)
                newsletter_chapters.append(chapter)

        # Build table of contents
        book.toc = [cover] + chapters + saved_chapters + newsletter_chapters

        # Add navigation files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Set spine (reading order)
        book.spine = ["nav", cover] + chapters + saved_chapters + newsletter_chapters

        # Generate filename and save
        filename = f"{date.strftime('%Y-%m-%d')}_{period}.epub"
        output_path = os.path.join(self.settings.output_dir, filename)

        # Ensure output directory exists
        os.makedirs(self.settings.output_dir, exist_ok=True)

        epub.write_epub(output_path, book)
        logger.info(f"Generated EPUB: {output_path} with {len(articles)} articles")

        return output_path

    def _create_cover(self, date: datetime, period: str, article_count: int) -> str:
        """
        Create the cover page HTML.

        Args:
            date: Digest date.
            period: Time period.
            article_count: Number of articles.

        Returns:
            HTML content for the cover.
        """
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>Epilogue Digest</title>
    <link rel="stylesheet" type="text/css" href="style/main.css"/>
</head>
<body>
    <div class="cover">
        <h1>Epilogue</h1>
        <p class="date">{date.strftime('%A, %B %d, %Y')}</p>
        <p>{period.capitalize()} Edition</p>
        <p>{article_count} articles</p>
    </div>
</body>
</html>"""

    def _create_section_divider(
        self, title: str, css: epub.EpubItem, file_name: str = "section_saved.xhtml"
    ) -> epub.EpubHtml:
        """Create a section divider page."""
        html_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{title}</title>
    <link rel="stylesheet" type="text/css" href="style/main.css"/>
</head>
<body>
    <div class="cover">
        <h1>{title}</h1>
    </div>
</body>
</html>"""

        page = epub.EpubHtml(
            title=title,
            file_name=file_name,
            lang="en",
        )
        page.content = html_content.encode("utf-8")
        page.add_item(css)
        return page

    def _create_chapter(
        self, article: ExtractedArticle, index: int, css: epub.EpubItem
    ) -> epub.EpubHtml:
        """
        Create a chapter for an article.

        Args:
            article: The extracted article.
            index: Chapter index.
            css: CSS item to attach.

        Returns:
            EpubHtml chapter.
        """
        # Escape HTML special chars in content and title
        def escape_html(text: str) -> str:
            return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        def looks_like_html(text: str) -> bool:
            return bool(re.search(r"<[a-zA-Z][^>]*>", text))

        title = escape_html(article.title)

        if looks_like_html(article.content):
            content_html = article.content
        else:
            content = escape_html(article.content)
            # Convert newlines to paragraphs
            paragraphs = content.split("\n\n")
            content_html = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())

        # Badge for summarized articles
        badge = ""
        if article.is_summary:
            badge = '<span class="summary-badge">AI Summary</span>'

        html_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{title}</title>
    <link rel="stylesheet" type="text/css" href="style/main.css"/>
</head>
<body>
    <div class="article">
        <h1>{title}{badge}</h1>
        <div class="article-meta">
            {f'<span>By {article.author}</span> | ' if article.author else ''}
            <span>{article.word_count} words</span>
            {' | <span>AI fallback</span>' if article.ai_failed else ''}
        </div>
        <div class="article-content">
            {content_html}
        </div>
        <p><a href="{article.url}">Read original</a></p>
    </div>
</body>
</html>"""

        chapter = epub.EpubHtml(
            title=article.title,
            file_name=f"chapter_{index:03d}.xhtml",
            lang="en",
        )
        chapter.content = html_content.encode("utf-8")
        chapter.add_item(css)

        return chapter

    def _create_newsletter_chapter(
        self, article: ExtractedArticle, index: int, css: epub.EpubItem
    ) -> epub.EpubHtml:
        """
        Create a chapter for a newsletter article.

        Inserts article content as raw HTML (already cleaned) rather than escaping it.
        """
        def escape_html(text: str) -> str:
            return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        title = escape_html(article.title)

        html_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{title}</title>
    <link rel="stylesheet" type="text/css" href="style/main.css"/>
</head>
<body>
    <div class="article">
        <h1>{title}<span class="summary-badge">Newsletter</span></h1>
        <div class="article-meta">
            {f'<span>From {escape_html(article.author)}</span> | ' if article.author else ''}
            <span>{article.word_count} words</span>
        </div>
        <div class="article-content">
            {article.content}
        </div>
    </div>
</body>
</html>"""

        chapter = epub.EpubHtml(
            title=article.title,
            file_name=f"newsletter_{index:03d}.xhtml",
            lang="en",
        )
        chapter.content = html_content.encode("utf-8")
        chapter.add_item(css)

        return chapter
