#!/usr/bin/env python3
"""Create and optionally poll a Ghostwriter one-off podcast episode."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

READY_STATUSES = {"ready", "failed"}
MIN_TEXT_CHARS = 80
MAX_TITLE_CHARS = 240
MAX_BRIEF_CHARS = 4_000
MAX_TEXT_CHARS = 120_000
DEFAULT_SPLIT_TARGET_CHARS = 90_000

EXIT_CONFIG = 2
EXIT_API = 3
EXIT_TIMEOUT = 4
EXIT_EPISODE_FAILED = 5
EXIT_DOWNLOAD = 6

FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*(?:\n|$)", re.DOTALL)
OBSIDIAN_COMMENT_RE = re.compile(r"%%.*?%%", re.DOTALL)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
WIKILINK_RE = re.compile(r"(!?)\[\[([^\]#|]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
BLOCK_ID_RE = re.compile(r"\s+\^[A-Za-z0-9_-]+(?=\s|$)")
TAG_RE = re.compile(r"(?<!\w)#([A-Za-z][A-Za-z0-9_/-]*)")


@dataclass
class SourceCandidate:
    """Local source material before conversion to Ghostwriter payload JSON."""

    title: str
    content: str
    kind: str
    origin: str
    order: int
    links: list[str] = field(default_factory=list)


def fail(message: str, code: int) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def normalize_api_base(value: str) -> str:
    base = value.strip().rstrip("/")
    if not base:
        fail("Ghostwriter base URL is empty", EXIT_CONFIG)
    if not base.endswith("/api"):
        base = f"{base}/api"
    return base


def default_env_files() -> list[Path]:
    return [Path.home() / ".env"]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.expanduser().read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        fail(f"Could not read env file {path}: {exc}", EXIT_CONFIG)

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_env_values(args: argparse.Namespace) -> dict[str, str]:
    paths: list[Path] = []
    if not args.no_default_env_files:
        paths.extend(path for path in default_env_files() if path.exists())
    paths.extend(Path(raw).expanduser() for raw in args.env_file)

    values: dict[str, str] = {}
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        values.update(parse_env_file(resolved))
    return values


def resolve_setting(
    *,
    explicit: str | None,
    env_names: list[str],
    env_values: dict[str, str],
    default: str | None = None,
    label: str,
) -> str:
    if explicit is not None:
        if explicit.strip():
            return explicit.strip()
        fail(f"--{label} was provided but empty", EXIT_CONFIG)

    for name in env_names:
        if name in os.environ:
            value = os.environ[name].strip()
            if value:
                return value
            fail(f"{name} is set in the process environment but empty", EXIT_CONFIG)

    for name in env_names:
        if name in env_values:
            value = env_values[name].strip()
            if value:
                return value
            fail(f"{name} is set in an env file but empty", EXIT_CONFIG)

    if default is not None:
        return default

    joined = "/".join(env_names)
    fail(
        f"No Ghostwriter {label} found. Set exported {joined}, "
        f"add it to --env-file, or pass --{label}.",
        EXIT_CONFIG,
    )


def request_json(
    *,
    method: str,
    api_base: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        f"{api_base}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        fail(f"Ghostwriter returned HTTP {exc.code}: {detail}", EXIT_API)
    except urllib.error.URLError as exc:
        fail(f"Could not reach Ghostwriter: {exc}", EXIT_API)

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fail(f"Ghostwriter returned non-JSON response: {raw[:500]}", EXIT_API)


def request_bytes(*, url: str, token: str) -> tuple[bytes, str | None]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "audio/*,*/*",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read(), response.headers.get("Content-Type")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        fail(f"Audio download returned HTTP {exc.code}: {detail}", EXIT_DOWNLOAD)
    except urllib.error.URLError as exc:
        fail(f"Could not download audio: {exc}", EXIT_DOWNLOAD)


def parse_titled_file(spec: str) -> tuple[str | None, Path]:
    if "=" in spec:
        title, raw_path = spec.split("=", 1)
        path = Path(raw_path).expanduser()
        if path.exists():
            return title.strip() or None, path
    path = Path(spec).expanduser()
    return None, path


def normalize_title(value: str) -> str:
    title = re.sub(r"\s+", " ", value).strip()
    return title[:MAX_TITLE_CHARS] or "Untitled source"


def normalize_episode_title(value: Any) -> str | None:
    if value is None:
        return None
    title = re.sub(r"\s+", " ", str(value)).strip()
    if len(title) > MAX_TITLE_CHARS:
        fail(f"Episode title exceeds {MAX_TITLE_CHARS} characters", EXIT_CONFIG)
    return title or None


def normalize_brief(value: Any) -> str | None:
    if value is None:
        return None
    brief = re.sub(r"\s+", " ", str(value)).strip()
    if len(brief) > MAX_BRIEF_CHARS:
        fail(f"Brief exceeds {MAX_BRIEF_CHARS} characters", EXIT_CONFIG)
    return brief or None


def build_context_lead_in(title: str | None, brief: str | None) -> str:
    lines: list[str] = []
    if title:
        lines.append(f"Episode title: {title}")
    if brief:
        lines.append(f"Caller brief: {brief}")
    return "\n".join(lines)


def combined_text_length(content: str, lead_in: str) -> int:
    return len(content) + len(lead_in) + (2 if lead_in else 0)


def clean_markdown(content: str) -> str:
    """Remove Obsidian/local Markdown noise while preserving readable prose."""
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    content = FRONTMATTER_RE.sub("", content)
    content = OBSIDIAN_COMMENT_RE.sub("", content)
    content = HTML_COMMENT_RE.sub("", content)
    content = WIKILINK_RE.sub(
        lambda m: "" if m.group(1) else (m.group(3) or m.group(2)),
        content,
    )
    content = BLOCK_ID_RE.sub("", content)
    content = TAG_RE.sub(lambda m: m.group(1).replace("/", " "), content)
    content = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", content)
    content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", content)
    content = re.sub(r"^[ \t]*[-*+][ \t]+\[[ xX]\][ \t]+", "- ", content, flags=re.MULTILINE)
    content = re.sub(r"^[ \t]*>{1,}[ \t]?", "", content, flags=re.MULTILINE)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return " ".join(content.split())


def extract_wikilinks(content: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for match in WIKILINK_RE.finditer(content):
        target = match.group(2).strip()
        if not target:
            continue
        key = target.lower()
        if key not in seen:
            seen.add(key)
            links.append(target)
    return links


def read_text_candidate(spec: str, *, order: int) -> SourceCandidate:
    title, path = parse_titled_file(spec)
    if not path.exists():
        fail(f"Text file not found: {path}", EXIT_CONFIG)
    if not path.is_file():
        fail(f"Text source is not a file: {path}", EXIT_CONFIG)
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        fail(f"Could not read {path} as UTF-8 text. Extract text before submitting.", EXIT_CONFIG)

    return SourceCandidate(
        title=normalize_title(title or path.stem.replace("-", " ").replace("_", " ")),
        content=clean_markdown(raw),
        kind="text_file",
        origin=str(path),
        order=order,
    )


def read_obsidian_note(path: Path, *, order: int) -> SourceCandidate:
    if not path.exists():
        fail(f"Obsidian note not found: {path}", EXIT_CONFIG)
    if not path.is_file():
        fail(f"Obsidian source is not a file: {path}", EXIT_CONFIG)
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        fail(f"Could not read Obsidian note as UTF-8: {path}", EXIT_CONFIG)

    return SourceCandidate(
        title=normalize_title(path.stem.replace("-", " ").replace("_", " ")),
        content=clean_markdown(raw),
        kind="obsidian_note",
        origin=str(path),
        order=order,
        links=extract_wikilinks(raw),
    )


def collect_markdown_files(folder: Path) -> list[Path]:
    if not folder.exists():
        fail(f"Obsidian folder not found: {folder}", EXIT_CONFIG)
    if not folder.is_dir():
        fail(f"Obsidian folder source is not a directory: {folder}", EXIT_CONFIG)
    return sorted(path for path in folder.rglob("*.md") if path.is_file())


def note_lookup_keys(path: Path, root: Path) -> list[str]:
    keys = {path.stem.lower()}
    try:
        rel = path.relative_to(root)
        keys.add(str(rel.with_suffix("")).lower())
        keys.add(str(rel).lower())
    except ValueError:
        pass
    return sorted(keys)


def build_note_index(roots: list[Path]) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for root in roots:
        if root.is_file() and root.suffix.lower() == ".md":
            files = [root]
            root_for_keys = root.parent
        elif root.is_dir():
            files = collect_markdown_files(root)
            root_for_keys = root
        else:
            continue
        for path in files:
            for key in note_lookup_keys(path, root_for_keys):
                index.setdefault(key, path)
    return index


def resolve_link(target: str, index: dict[str, Path]) -> Path | None:
    normalized = target.strip().removesuffix(".md").lower()
    return index.get(normalized) or index.get(f"{normalized}.md")


def split_text(content: str, *, target_chars: int) -> list[str]:
    if len(content) <= target_chars:
        return [content]

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n|(?<=\.)\s+", content) if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        if len(paragraph) > target_chars:
            if current:
                chunks.append(" ".join(current).strip())
                current = []
                current_len = 0
            for start in range(0, len(paragraph), target_chars):
                chunks.append(paragraph[start : start + target_chars].strip())
            continue

        next_len = current_len + len(paragraph) + (1 if current else 0)
        if current and next_len > target_chars:
            chunks.append(" ".join(current).strip())
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len = next_len

    if current:
        chunks.append(" ".join(current).strip())

    if len(chunks) >= 2 and len(chunks[-1]) < MIN_TEXT_CHARS:
        needed = MIN_TEXT_CHARS - len(chunks[-1])
        previous = chunks[-2]
        if len(previous) - needed >= MIN_TEXT_CHARS:
            chunks[-2] = previous[:-needed].strip()
            chunks[-1] = f"{previous[-needed:]} {chunks[-1]}".strip()

    return [chunk for chunk in chunks if chunk]


def candidate_to_sources(
    candidate: SourceCandidate,
    *,
    split_target_chars: int,
    lead_in: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    content = candidate.content.strip()
    if len(content) < MIN_TEXT_CHARS:
        warnings.append(f"Skipped short source: {candidate.origin}")
        return [], [], warnings

    max_content_chars = MAX_TEXT_CHARS - len(lead_in) - (2 if lead_in else 0)
    if max_content_chars < MIN_TEXT_CHARS:
        fail("Title/brief context leaves no room for source content", EXIT_CONFIG)

    effective_target = min(split_target_chars, max_content_chars)
    chunks = split_text(content, target_chars=effective_target)
    sources: list[dict[str, str]] = []
    metadata: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        if len(chunk) < MIN_TEXT_CHARS:
            fail(f"Prepared chunk is too short to submit: {candidate.origin}", EXIT_CONFIG)
        if combined_text_length(chunk, lead_in) > MAX_TEXT_CHARS:
            fail(
                "Prepared chunk exceeds Ghostwriter's combined title/brief/source "
                f"limit: {candidate.origin}",
                EXIT_CONFIG,
            )
        title = candidate.title
        if len(chunks) > 1:
            title = f"{title} - Part {index}"
        digest = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
        sources.append({"type": "text", "title": title, "content": chunk})
        metadata.append(
            {
                "title": title,
                "kind": candidate.kind,
                "origin": candidate.origin,
                "chars": len(chunk),
                "words": len(chunk.split()),
                "sha256": digest,
                "order": candidate.order,
            }
        )
    return sources, metadata, warnings


def metadata_for_source(source: dict[str, Any], *, order: int) -> dict[str, Any]:
    if source.get("type") == "text":
        content = str(source.get("content") or "")
        return {
            "title": source.get("title") or f"Text source {order + 1}",
            "kind": "source_json",
            "origin": "source_json",
            "chars": len(content),
            "words": len(content.split()),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "order": order,
        }
    return {
        "title": source.get("title") or source.get("url") or f"URL source {order + 1}",
        "kind": "url",
        "origin": source.get("url") or "source_json",
        "chars": None,
        "words": None,
        "sha256": None,
        "order": order,
    }


def parse_titled_url(spec: str) -> dict[str, str]:
    title = None
    url = spec.strip()
    if "=" in spec:
        left, right = spec.split("=", 1)
        if right.startswith(("http://", "https://")):
            title = left.strip() or None
            url = right.strip()
    if not url.startswith(("http://", "https://")):
        fail(f"URL sources must start with http:// or https://: {url}", EXIT_CONFIG)
    source = {"type": "url", "url": url}
    if title:
        source["title"] = title
    return source


def load_source_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except OSError as exc:
        fail(f"Could not read source JSON: {exc}", EXIT_CONFIG)
    except json.JSONDecodeError as exc:
        fail(f"Invalid source JSON: {exc}", EXIT_CONFIG)

    if isinstance(data, list):
        return {"sources": data}
    if isinstance(data, dict):
        if "payload" in data and isinstance(data["payload"], dict):
            return dict(data["payload"])
        return data
    fail("Source JSON must be either a payload object or a sources array", EXIT_CONFIG)


def build_local_candidates(args: argparse.Namespace) -> tuple[list[SourceCandidate], list[str]]:
    warnings: list[str] = []
    candidates: list[SourceCandidate] = []
    order = 0

    for spec in args.text_file:
        candidates.append(read_text_candidate(spec, order=order))
        order += 1

    explicit_note_paths = [Path(raw).expanduser() for raw in args.obsidian_note]
    folder_paths = [Path(raw).expanduser() for raw in args.obsidian_folder]
    selected_note_paths: list[Path] = []
    selected_note_paths.extend(explicit_note_paths)
    for folder in folder_paths:
        selected_note_paths.extend(collect_markdown_files(folder))

    seen_note_paths: set[Path] = set()
    note_candidates: list[SourceCandidate] = []
    for path in selected_note_paths:
        resolved = path.resolve()
        if resolved in seen_note_paths:
            warnings.append(f"Skipped duplicate note path: {path}")
            continue
        seen_note_paths.add(resolved)
        note_candidates.append(read_obsidian_note(path, order=order))
        order += 1

    if args.include_linked_notes and note_candidates:
        roots = [path.parent for path in explicit_note_paths]
        roots.extend(folder_paths)
        roots.extend(Path(raw).expanduser() for raw in args.obsidian_root)
        index = build_note_index([root for root in roots if root.exists()])
        for candidate in list(note_candidates):
            for link in candidate.links:
                linked_path = resolve_link(link, index)
                if linked_path is None:
                    warnings.append(f"Could not resolve wikilink '{link}' from {candidate.origin}")
                    continue
                resolved = linked_path.resolve()
                if resolved in seen_note_paths:
                    continue
                seen_note_paths.add(resolved)
                note_candidates.append(read_obsidian_note(linked_path, order=order))
                order += 1

    candidates.extend(note_candidates)
    return candidates, warnings


def build_payload_and_preview(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    payload: dict[str, Any] = {}
    warnings: list[str] = []
    metadata: list[dict[str, Any]] = []

    if args.source_json:
        payload.update(load_source_json(Path(args.source_json)))

    title = normalize_episode_title(args.title if args.title is not None else payload.get("title"))
    brief = normalize_brief(args.brief if args.brief is not None else payload.get("brief"))
    lead_in = build_context_lead_in(title, brief)

    sources: list[dict[str, Any]] = list(payload.get("sources") or [])
    metadata.extend(metadata_for_source(source, order=index) for index, source in enumerate(sources))
    candidates, candidate_warnings = build_local_candidates(args)
    warnings.extend(candidate_warnings)

    for candidate in sorted(candidates, key=lambda item: item.order):
        prepared, prepared_metadata, prepared_warnings = candidate_to_sources(
            candidate,
            split_target_chars=args.split_target_chars,
            lead_in=lead_in,
        )
        sources.extend(prepared)
        metadata.extend(prepared_metadata)
        warnings.extend(prepared_warnings)

    url_sources = [parse_titled_url(spec) for spec in args.url]
    sources.extend(url_sources)
    metadata.extend(
        {
            "title": source.get("title") or source["url"],
            "kind": "url",
            "origin": source["url"],
            "chars": None,
            "words": None,
            "sha256": None,
            "order": len(metadata),
        }
        for source in url_sources
    )

    deduped_sources: list[dict[str, Any]] = []
    deduped_metadata: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for source, meta in zip(sources, metadata, strict=False):
        if source.get("type") == "text":
            content = str(source.get("content") or "")
            key = "text:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
        else:
            key = "url:" + str(source.get("url") or "").strip().lower()
        if key in seen_keys:
            warnings.append(f"Skipped duplicate source: {source.get('title') or source.get('url')}")
            continue
        seen_keys.add(key)
        deduped_sources.append(source)
        deduped_metadata.append(meta)

    if not deduped_sources:
        fail("Provide at least one usable source", EXIT_CONFIG)
    if len(deduped_sources) > 20:
        fail(
            f"Prepared {len(deduped_sources)} sources, but Ghostwriter supports at most 20",
            EXIT_CONFIG,
        )

    payload["sources"] = deduped_sources
    for source in deduped_sources:
        if source.get("type") != "text":
            continue
        content = str(source.get("content") or "")
        if combined_text_length(content, lead_in) > MAX_TEXT_CHARS:
            fail(
                "Text source exceeds Ghostwriter's combined title/brief/source "
                f"limit: {source.get('title') or 'untitled source'}",
                EXIT_CONFIG,
            )

    payload["title"] = title
    payload["brief"] = brief

    preview = {
        "title": title,
        "brief": brief,
        "source_count": len(deduped_sources),
        "text_source_count": sum(1 for source in deduped_sources if source.get("type") == "text"),
        "url_source_count": sum(1 for source in deduped_sources if source.get("type") == "url"),
        "total_words": sum(meta.get("words") or 0 for meta in deduped_metadata),
        "warnings": warnings,
        "sources": deduped_metadata,
    }
    payload["_preview"] = preview
    return payload, preview


def write_preview(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)
    if output:
        path = Path(output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(str(path))
    else:
        print(text)


def poll_episode(
    *,
    api_base: str,
    token: str,
    episode_id: str,
    interval_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status = ""
    while time.monotonic() < deadline:
        detail = request_json(
            method="GET",
            api_base=api_base,
            path=f"/podcast/episodes/{episode_id}",
            token=token,
        )
        status = str(detail.get("status") or "")
        if status != last_status:
            print(f"episode {episode_id}: {status}", file=sys.stderr)
            last_status = status
        if status in READY_STATUSES:
            return detail
        time.sleep(interval_seconds)
    fail(f"Timed out waiting for episode {episode_id}", EXIT_TIMEOUT)


def output_path_for_episode(path: str | None, episode_id: str) -> Path:
    if path:
        candidate = Path(path).expanduser()
        if candidate.exists() and candidate.is_dir():
            return candidate / f"ghostwriter-podcast-{episode_id}.mp3"
        return candidate
    return Path.cwd() / f"ghostwriter-podcast-{episode_id}.mp3"


def download_episode(
    *,
    api_base: str,
    token: str,
    detail: dict[str, Any],
    output: str | None,
) -> Path:
    episode_id = str(detail.get("id") or detail.get("episode_id") or "")
    if not episode_id:
        fail("Cannot download audio: episode detail did not include an id", EXIT_DOWNLOAD)

    raw_url = detail.get("download_url") or detail.get("stream_url")
    if not raw_url:
        fail("Cannot download audio: episode detail did not include a download URL", EXIT_DOWNLOAD)
    url = str(raw_url)
    if url.startswith("/"):
        root = api_base.removesuffix("/api") + "/"
        url = urljoin(root, url.lstrip("/"))

    data, content_type = request_bytes(url=url, token=token)
    if content_type and "json" in content_type.lower():
        fail(f"Audio download returned JSON instead of audio from {url}", EXIT_DOWNLOAD)

    path = output_path_for_episode(output, episode_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_bytes(data)
    except OSError as exc:
        fail(f"Could not write audio to {path}: {exc}", EXIT_DOWNLOAD)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Ghostwriter one-off podcast episode."
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Ghostwriter base URL, with or without /api.",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Read Ghostwriter settings from a .env file. Repeatable.",
    )
    parser.add_argument(
        "--no-default-env-files",
        action="store_true",
        help="Do not automatically read ~/.env when present.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Ghostwriter API token or JWT. Defaults to GHOSTWRITER_TOKEN/GW_TOKEN.",
    )
    parser.add_argument("--title", help="Episode title.")
    parser.add_argument("--brief", help="Focus instructions for the episode.")
    parser.add_argument(
        "--text-file",
        action="append",
        default=[],
        metavar="[TITLE=]PATH",
        help="UTF-8 text or Markdown file to submit as a source. Repeatable.",
    )
    parser.add_argument(
        "--obsidian-note",
        action="append",
        default=[],
        metavar="PATH",
        help="Obsidian Markdown note to clean and submit. Repeatable.",
    )
    parser.add_argument(
        "--obsidian-folder",
        action="append",
        default=[],
        metavar="PATH",
        help="Folder of Obsidian .md notes to submit recursively. Repeatable.",
    )
    parser.add_argument(
        "--obsidian-root",
        action="append",
        default=[],
        metavar="PATH",
        help="Extra vault root used to resolve wikilinks when including linked notes.",
    )
    parser.add_argument(
        "--include-linked-notes",
        action="store_true",
        help="Include one-hop wikilink targets found in selected Obsidian notes.",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        metavar="[TITLE=]URL",
        help="Reachable article URL to submit as a source. Repeatable.",
    )
    parser.add_argument(
        "--source-json",
        help="JSON file containing either a payload, preview payload, or sources array.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Build and print/write the Ghostwriter payload without submitting it.",
    )
    parser.add_argument(
        "--preview-output",
        help="Write --preview JSON to this path instead of stdout.",
    )
    parser.add_argument(
        "--split-target-chars",
        type=int,
        default=DEFAULT_SPLIT_TARGET_CHARS,
        help=f"Target size for splitting long text sources. Default: {DEFAULT_SPLIT_TARGET_CHARS}.",
    )
    parser.add_argument(
        "--poll",
        action="store_true",
        help="Poll the episode until it is ready or failed.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Poll until ready and download the generated audio.",
    )
    parser.add_argument(
        "--output",
        help="Audio output path. If a directory is provided, a filename is generated.",
    )
    parser.add_argument("--poll-interval", type=float, default=10.0)
    parser.add_argument("--poll-timeout", type=float, default=1800.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.split_target_chars < MIN_TEXT_CHARS or args.split_target_chars > MAX_TEXT_CHARS:
        fail(
            f"--split-target-chars must be between {MIN_TEXT_CHARS} and {MAX_TEXT_CHARS}",
            EXIT_CONFIG,
        )

    payload, _preview = build_payload_and_preview(args)
    if args.preview:
        write_preview(payload, args.preview_output)
        return 0

    env_values = load_env_values(args)
    token = resolve_setting(
        explicit=args.token,
        env_names=["GHOSTWRITER_TOKEN", "GW_TOKEN"],
        env_values=env_values,
        label="token",
    )
    base_url = resolve_setting(
        explicit=args.base_url,
        env_names=["GHOSTWRITER_BASE_URL", "GW_BASE"],
        env_values=env_values,
        default="http://gateway.local:8158",
        label="base-url",
    )

    api_base = normalize_api_base(base_url)
    submit_payload = {
        key: payload[key]
        for key in ("title", "brief", "sources")
        if key in payload
    }
    created = request_json(
        method="POST",
        api_base=api_base,
        path="/podcast/episodes/one-off",
        token=token,
        payload=submit_payload,
    )

    should_poll = args.poll or args.download or bool(args.output)
    if not should_poll:
        print(json.dumps(created, indent=2, sort_keys=True))
        return 0

    episode_id = created.get("episode_id")
    if not episode_id:
        print(json.dumps(created, indent=2, sort_keys=True))
        fail("Create response did not include episode_id", EXIT_API)

    final = poll_episode(
        api_base=api_base,
        token=token,
        episode_id=str(episode_id),
        interval_seconds=args.poll_interval,
        timeout_seconds=args.poll_timeout,
    )

    if args.download or args.output:
        if final.get("status") != "ready":
            print(json.dumps(final, indent=2, sort_keys=True))
            return EXIT_EPISODE_FAILED
        path = download_episode(
            api_base=api_base,
            token=token,
            detail=final,
            output=args.output,
        )
        final["downloaded_path"] = str(path)

    print(json.dumps(final, indent=2, sort_keys=True))
    return 0 if final.get("status") == "ready" else EXIT_EPISODE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
