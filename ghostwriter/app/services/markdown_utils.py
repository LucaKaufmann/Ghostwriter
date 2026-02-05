"""Lightweight Markdown-to-HTML conversion utilities."""

from __future__ import annotations

import re


def markdown_to_html_basic(markdown: str) -> str:
    """
    Convert a small subset of Markdown to HTML.

    Supports:
    - Headings (#, ##, ###)
    - Bullet lists (-, *, •)
    - Bold (**text**) and italics (*text*)
    - Paragraphs (blank-line separated)
    """
    if not markdown:
        return ""

    text = markdown.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = text.split("\n")

    blocks: list[str] = []
    current_paragraph: list[str] = []
    current_list: list[str] = []

    def flush_paragraph() -> None:
        if not current_paragraph:
            return
        paragraph_text = " ".join(s.strip() for s in current_paragraph if s.strip())
        if paragraph_text:
            blocks.append(f"<p>{_inline_format(paragraph_text)}</p>")
        current_paragraph.clear()

    def flush_list() -> None:
        if not current_list:
            return
        items = "".join(f"<li>{_inline_format(item)}</li>" for item in current_list)
        blocks.append(f"<ul>{items}</ul>")
        current_list.clear()

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            flush_list()
            flush_paragraph()
            continue

        if line.startswith("### "):
            flush_list()
            flush_paragraph()
            blocks.append(f"<h3>{_inline_format(line[4:])}</h3>")
            continue

        if line.startswith("## "):
            flush_list()
            flush_paragraph()
            blocks.append(f"<h2>{_inline_format(line[3:])}</h2>")
            continue

        if line.startswith("# "):
            flush_list()
            flush_paragraph()
            blocks.append(f"<h1>{_inline_format(line[2:])}</h1>")
            continue

        if line.startswith(("- ", "* ", "• ")):
            flush_paragraph()
            current_list.append(line[2:].strip())
            continue

        current_paragraph.append(line)

    flush_list()
    flush_paragraph()

    return "\n".join(blocks)


def _inline_format(text: str) -> str:
    formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    formatted = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", formatted)
    return formatted
