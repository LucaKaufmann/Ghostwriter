"""Digest content formatting helpers for EPUB and web reader output."""

from __future__ import annotations

import html
import re

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=(?:['\"])?[A-Z0-9])")
_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_ORDERED_LIST_RE = re.compile(r"^\d+[.)]\s+")
_UNORDERED_LIST_RE = re.compile(r"^[-*•]\s+")
_TRAILING_PUNCT_RE = re.compile(r"[.!?]\s*$")

_PARAGRAPH_MAX_CHARS = 320
_PARAGRAPH_TARGET_CHARS = 220
_MAX_SENTENCES_PER_PARAGRAPH = 3


def looks_like_html(text: str) -> bool:
    """Return True when the text appears to already contain HTML markup."""
    return bool(re.search(r"<[a-zA-Z][^>]*>", text))


def format_digest_content_to_html(content: str) -> str:
    """
    Convert digest content into readable HTML.

    Existing HTML is returned untouched. Plain text is converted into paragraphs
    with lightweight heading/list handling and paragraph expansion for dense text.
    """
    if not content:
        return ""

    if looks_like_html(content):
        return content

    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""

    blocks = [block.strip() for block in re.split(r"\n\s*\n+", normalized) if block.strip()]
    rendered_blocks: list[str] = []

    for block in blocks:
        rendered_blocks.extend(_render_text_block(block))

    return "\n".join(rendered_blocks)


def _render_text_block(block: str) -> list[str]:
    lines = [line.strip() for line in block.split("\n") if line.strip()]
    if not lines:
        return []

    if _is_list_block(lines):
        return [_render_list(lines)]

    heading = _parse_markdown_heading(lines[0])
    if heading:
        tag, text = heading
        rendered = [f"<{tag}>{_inline_format(text)}</{tag}>"]
        remainder = " ".join(lines[1:]).strip()
        if remainder:
            rendered.extend(_render_paragraphs(remainder))
        return rendered

    if _looks_like_inline_heading(lines[0]):
        rendered = [f"<h3>{_inline_format(lines[0].rstrip(':').strip())}</h3>"]
        remainder = " ".join(lines[1:]).strip()
        if remainder:
            rendered.extend(_render_paragraphs(remainder))
        return rendered

    merged = " ".join(lines)
    return _render_paragraphs(merged)


def _render_paragraphs(text: str) -> list[str]:
    paragraphs = _split_long_paragraph(text)
    return [f"<p>{_inline_format(paragraph)}</p>" for paragraph in paragraphs if paragraph]


def _split_long_paragraph(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []

    sentences = _SENTENCE_SPLIT_RE.split(compact)
    if len(sentences) <= 1:
        if len(compact) <= _PARAGRAPH_MAX_CHARS:
            return [compact]
        return _chunk_by_words(compact, _PARAGRAPH_TARGET_CHARS)

    chunks: list[str] = []
    current: list[str] = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        candidate = " ".join([*current, sentence]).strip()
        if current and (
            len(candidate) > _PARAGRAPH_MAX_CHARS
            or len(current) >= _MAX_SENTENCES_PER_PARAGRAPH
        ):
            chunks.append(" ".join(current).strip())
            current = [sentence]
            continue

        current.append(sentence)

    if current:
        chunks.append(" ".join(current).strip())

    if len(chunks) == 1 and len(chunks[0]) > _PARAGRAPH_MAX_CHARS:
        return _chunk_by_words(chunks[0], _PARAGRAPH_TARGET_CHARS)

    return chunks


def _chunk_by_words(text: str, target_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    current: list[str] = []

    for word in words:
        candidate = " ".join([*current, word]).strip()
        if current and len(candidate) > target_chars:
            chunks.append(" ".join(current).strip())
            current = [word]
            continue
        current.append(word)

    if current:
        chunks.append(" ".join(current).strip())

    return chunks


def _parse_markdown_heading(line: str) -> tuple[str, str] | None:
    match = _MARKDOWN_HEADING_RE.match(line.strip())
    if not match:
        return None

    level = min(len(match.group(1)), 4)
    text = match.group(2).strip()
    if not text:
        return None
    return f"h{level}", text


def _is_list_block(lines: list[str]) -> bool:
    if not lines:
        return False
    return all(_ORDERED_LIST_RE.match(line) or _UNORDERED_LIST_RE.match(line) for line in lines)


def _render_list(lines: list[str]) -> str:
    ordered = all(_ORDERED_LIST_RE.match(line) for line in lines)
    tag = "ol" if ordered else "ul"
    items: list[str] = []

    for line in lines:
        if ordered:
            item_text = _ORDERED_LIST_RE.sub("", line, count=1).strip()
        else:
            item_text = _UNORDERED_LIST_RE.sub("", line, count=1).strip()
        items.append(f"<li>{_inline_format(item_text)}</li>")

    return f"<{tag}>{''.join(items)}</{tag}>"


def _looks_like_inline_heading(line: str) -> bool:
    candidate = line.strip()
    if not candidate:
        return False
    if _TRAILING_PUNCT_RE.search(candidate):
        return False
    if re.search(r"https?://|www\.", candidate, re.IGNORECASE):
        return False

    normalized = candidate.rstrip(":").strip()
    if len(normalized) < 5 or len(normalized) > 90:
        return False

    words = normalized.split()
    if len(words) < 2 or len(words) > 12:
        return False

    alpha_words = [w for w in words if any(ch.isalpha() for ch in w)]
    if len(alpha_words) < 2:
        return False

    title_case_ratio = sum(1 for word in alpha_words if word[0].isupper()) / len(alpha_words)
    all_caps = normalized.isupper()
    return candidate.endswith(":") or all_caps or title_case_ratio >= 0.65


def _inline_format(text: str) -> str:
    escaped = html.escape(text.strip(), quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped
