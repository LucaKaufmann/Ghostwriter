"""EPUB generation service using EbookLib."""

import logging
import os
import re
from datetime import datetime
from html import escape as html_escape
from uuid import uuid4

from ebooklib import epub

from app.core.config import Settings, get_settings
from app.services.content_processor import ExtractedArticle
from app.services.cover_image_service import CoverImage
from app.services.digest_content_formatter import format_digest_content_to_html

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
    .cover-art {
        width: 100%;
        max-width: 900px;
        height: auto;
        margin: 0 auto 1.5em;
        display: block;
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
        media_articles: list[ExtractedArticle] | None = None,
        cover_image: CoverImage | None = None,
        output_filename: str | None = None,
    ) -> str:
        """
        Generate an EPUB file from extracted articles.

        Args:
            articles: List of ExtractedArticle objects.
            period: Time period (morning, noon, evening, manual).
            date: Date for the digest (defaults to now).
            saved_articles: Wallabag articles.
            newsletter_articles: Newsletter articles.
            media_articles: Completed media items (podcast/YouTube transcripts).
            cover_image: Optional generated cover image to embed.
            output_filename: Stored EPUB filename to write.

        Returns:
            Path to the generated EPUB file.
        """
        if date is None:
            date = datetime.utcnow()

        all_articles: list[ExtractedArticle] = list(articles)
        if saved_articles:
            all_articles.extend(saved_articles)
        if newsletter_articles:
            all_articles.extend(newsletter_articles)
        if media_articles:
            all_articles.extend(media_articles)

        # Split into regular articles and media (podcast/youtube) articles
        regular_articles = [a for a in all_articles if a.content_type == "article"]
        media_articles = [a for a in all_articles if a.content_type != "article"]

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

        cover_image_href: str | None = None
        if cover_image:
            cover_image_href = self._cover_image_file_name(cover_image.media_type)
            # Register canonical cover metadata for EPUB readers while we keep
            # our custom cover.xhtml page in the reading order.
            book.set_cover(cover_image_href, cover_image.data, create_page=False)

        # Create cover page
        cover_content = self._create_cover(
            date,
            period,
            len(all_articles),
            cover_image_href=cover_image_href,
        )
        cover = epub.EpubHtml(
            title="Cover",
            file_name="cover.xhtml",
            lang="en",
        )
        cover.content = cover_content.encode("utf-8")
        cover.add_item(css)
        book.add_item(cover)
        book.guide.append({"type": "cover", "title": "Cover", "href": cover.file_name})

        # Create one chapter per feed with sub-chapters for each feed article.
        toc_entries: list = [cover]
        spine_entries: list = ["nav", cover]
        feed_index = 0
        for feed_title, feed_articles in self._group_articles_by_feed(regular_articles):
            feed_index += 1
            feed_slug = self._slugify(feed_title)
            feed_section = self._create_section_divider(
                feed_title,
                css,
                file_name=f"feed_{feed_index:03d}_{feed_slug}.xhtml",
            )
            book.add_item(feed_section)
            spine_entries.append(feed_section)

            feed_chapters: list[epub.EpubHtml] = []
            for article_index, article in enumerate(feed_articles, start=1):
                chapter = self._create_chapter(
                    article,
                    css,
                    file_name=(
                        f"feed_{feed_index:03d}_article_"
                        f"{article_index:03d}_{feed_slug}.xhtml"
                    ),
                )
                book.add_item(chapter)
                feed_chapters.append(chapter)
                spine_entries.append(chapter)

            toc_entries.append(
                (epub.Section(feed_title), [feed_section] + feed_chapters)
            )

        # Append media articles (podcasts, YouTube) in separate sections at the end
        media_by_type: dict[str, list[ExtractedArticle]] = {}
        for a in media_articles:
            media_by_type.setdefault(a.content_type, []).append(a)

        section_labels = {"podcast": "Podcasts", "youtube": "YouTube"}
        for content_type, type_articles in media_by_type.items():
            section_title = section_labels.get(content_type, content_type.capitalize())
            for feed_title, feed_articles in self._group_articles_by_feed(
                type_articles
            ):
                feed_index += 1
                group_title = f"{section_title}: {feed_title}"
                feed_slug = self._slugify(group_title)
                feed_section = self._create_section_divider(
                    group_title,
                    css,
                    file_name=f"feed_{feed_index:03d}_{feed_slug}.xhtml",
                )
                book.add_item(feed_section)
                spine_entries.append(feed_section)

                feed_chapters_media: list[epub.EpubHtml] = []
                for article_index, article in enumerate(feed_articles, start=1):
                    chapter = self._create_chapter(
                        article,
                        css,
                        file_name=(
                            f"feed_{feed_index:03d}_article_"
                            f"{article_index:03d}_{feed_slug}.xhtml"
                        ),
                    )
                    book.add_item(chapter)
                    feed_chapters_media.append(chapter)
                    spine_entries.append(chapter)

                toc_entries.append(
                    (epub.Section(group_title), [feed_section] + feed_chapters_media)
                )

        # Build table of contents
        book.toc = toc_entries

        # Add navigation files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Set spine (reading order)
        book.spine = spine_entries

        # Generate filename and save
        filename = output_filename or f"{date.strftime('%Y-%m-%d')}_{period}.epub"
        output_path = os.path.join(self.settings.output_dir, filename)

        # Ensure output directory exists
        os.makedirs(self.settings.output_dir, exist_ok=True)

        epub.write_epub(output_path, book)
        logger.info(f"Generated EPUB: {output_path} with {len(all_articles)} articles")

        return output_path

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "feed"

    @staticmethod
    def _group_articles_by_feed(
        articles: list[ExtractedArticle],
    ) -> list[tuple[str, list[ExtractedArticle]]]:
        grouped: dict[str, list[ExtractedArticle]] = {}
        for article in articles:
            title = article.feed_title.strip() or "Unknown Feed"
            if title not in grouped:
                grouped[title] = []
            grouped[title].append(article)
        return list(grouped.items())

    @staticmethod
    def _cover_image_file_name(media_type: str) -> str:
        normalized = media_type.split(";")[0].strip().lower()
        if normalized == "image/jpeg":
            ext = "jpg"
        elif normalized == "image/webp":
            ext = "webp"
        elif normalized == "image/gif":
            ext = "gif"
        else:
            ext = "png"
        return f"images/cover.{ext}"

    def _create_cover(
        self,
        date: datetime,
        period: str,
        article_count: int,
        cover_image_href: str | None = None,
    ) -> str:
        """
        Create the cover page HTML.

        Args:
            date: Digest date.
            period: Time period.
            article_count: Number of articles.
            cover_image_href: Optional path to an embedded cover image.

        Returns:
            HTML content for the cover.
        """
        cover_image_html = ""
        if cover_image_href:
            cover_image_html = f'<img class="cover-art" src="{cover_image_href}" alt="Digest cover image"/>'

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>Epilogue Digest</title>
    <link rel="stylesheet" type="text/css" href="style/main.css"/>
</head>
<body>
    <div class="cover">
        {cover_image_html}
        <h1>Epilogue</h1>
        <p class="date">{date.strftime("%A, %B %d, %Y")}</p>
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
        self,
        article: ExtractedArticle,
        css: epub.EpubItem,
        file_name: str,
    ) -> epub.EpubHtml:
        """
        Create a chapter for an article.

        Args:
            article: The extracted article.
            css: CSS item to attach.
            file_name: Chapter file name.

        Returns:
            EpubHtml chapter.
        """
        title = html_escape(article.title, quote=False)
        content_html = format_digest_content_to_html(article.content)
        article_url = html_escape(article.url, quote=True)

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
            {f"<span>By {article.author}</span> | " if article.author else ""}
            <span>{article.word_count} words</span>
            {" | <span>AI fallback</span>" if article.ai_failed else ""}
        </div>
        <div class="article-content">
            {content_html}
        </div>
        <p><a href="{article_url}">Read original</a></p>
    </div>
</body>
</html>"""

        chapter = epub.EpubHtml(
            title=article.title,
            file_name=file_name,
            lang="en",
        )
        chapter.content = html_content.encode("utf-8")
        chapter.add_item(css)

        return chapter
