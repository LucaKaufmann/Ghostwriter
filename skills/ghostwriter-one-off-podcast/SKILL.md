---
name: ghostwriter-one-off-podcast
description: Create ad hoc Ghostwriter podcast episodes from user-provided documents, article URLs, notes, or extracted text, then poll until the episode is ready in the private podcast feed.
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [ghostwriter, podcast, openclaw, documents, audio]
    config:
      - key: ghostwriter.base_url
        description: Base URL for Ghostwriter without the /api suffix
        default: "http://gateway.local:8158"
        prompt: Ghostwriter base URL
      - key: ghostwriter.token_env
        description: Environment variable containing the Ghostwriter API token or JWT
        default: "GHOSTWRITER_TOKEN"
        prompt: Ghostwriter token environment variable
---

# Ghostwriter One-Off Podcast

Use this skill when Luca asks to turn one or more documents, notes, article URLs, or research sources into a one-off Ghostwriter podcast episode.

## Requirements

- Ghostwriter endpoint: `http://gateway.local:8158/api/podcast/episodes/one-off`
- Authentication: `Authorization: Bearer <token>`
- Token source: prefer `$GHOSTWRITER_TOKEN`, then `$GW_TOKEN`, then a `--env-file` such as `~/.env`; do not ask Luca to paste secrets into chat if an environment variable or env file can be used.
- Phase 1 accepts only:
  - `type: "url"` for reachable article URLs
  - `type: "text"` for pasted or extracted document text
- Limits: 1-20 sources, each text source under 120000 characters, each source should have at least about 80 characters of usable content.

## Workflow

1. Collect the requested source material.
2. For Obsidian notes, pass note/folder paths to the helper instead of manually copying Markdown.
3. Preview the exact Ghostwriter payload before submitting when the request has multiple notes or linked-note expansion.
4. Create the episode with `scripts/create_one_off_podcast.py`.
5. Poll until status is `ready` or `failed`.
6. Download the audio when Luca asked for a file or automation output.
7. Report the episode id, final status, source count, downloaded path, and feed/download URL if ready. If failed, report `error_message`.

## Helper Script

Use the bundled script whenever possible:

```bash
python3 ~/clawd/skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py \
  --env-file ~/.env \
  --title "OpenClaw planning brief" \
  --brief "Explain the source documents, tradeoffs, and next actions." \
  --text-file "OpenClaw Notes=/path/to/openclaw-notes.txt" \
  --url "https://example.com/article" \
  --download \
  --output ~/Downloads/openclaw-planning-brief.mp3
```

Obsidian preview workflow:

```bash
python3 ~/clawd/skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py \
  --title "OpenClaw notes podcast" \
  --brief "Explain these notes as a concise conversational briefing." \
  --obsidian-note "/path/to/Vault/OpenClaw.md" \
  --obsidian-folder "/path/to/Vault/Projects/OpenClaw" \
  --include-linked-notes \
  --preview \
  --preview-output /tmp/openclaw-podcast-preview.json
```

Submit from the preview:

```bash
python3 ~/clawd/skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py \
  --env-file ~/.env \
  --source-json /tmp/openclaw-podcast-preview.json \
  --download \
  --output ~/Downloads/openclaw-notes.mp3
```

Environment overrides:

```bash
export GHOSTWRITER_BASE_URL="http://gateway.local:8158"
export GHOSTWRITER_TOKEN="gw_..."
```

If using a `.env` file, pass it directly instead of relying on `source ~/.env`; sourced shell variables only reach Python if they are exported:

```bash
python3 ~/clawd/skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py \
  --env-file ~/.env \
  --text-file "Note=/path/to/note.md" \
  --download
```

The script automatically reads `~/.env` when present, unless `--no-default-env-files` is passed. It does not automatically read `./.env`; pass project-local env files with `--env-file .env` so the destination for authenticated requests is explicit. CLI flags override exported environment variables, which override env-file values.

The script prints JSON. On creation it includes `episode_id`, `digest_ids`, and `status`. With `--poll`, it prints the final episode detail. With `--download` or `--output`, it polls until ready, saves the MP3, and adds `downloaded_path` to the final JSON.

Preview JSON includes the submit-ready `title`, `brief`, and `sources` fields plus `_preview` metadata with source counts, word counts, warnings, source origins, and content hashes. The helper accepts its own preview output via `--source-json`.

Exit codes:

- `0`: episode ready, and download succeeded if requested
- `2`: local configuration or input error
- `3`: Ghostwriter API/network error
- `4`: polling timed out
- `5`: episode reached `failed`
- `6`: audio download failed

## Payload Shape

When calling the API directly, send:

```json
{
  "title": "Episode title",
  "brief": "What the episode should focus on.",
  "sources": [
    {
      "type": "text",
      "title": "Document title",
      "content": "Extracted document text..."
    },
    {
      "type": "url",
      "title": "Optional article title",
      "url": "https://example.com/article"
    }
  ]
}
```

## Operating Rules

- Keep documents in user-provided order unless Luca asks for a different structure.
- Prefer extracted text for private/local documents; Ghostwriter cannot fetch files from Luca's machine.
- For Obsidian, prefer `--obsidian-note` and `--obsidian-folder`; the helper strips YAML frontmatter, comments, embeds, wikilinks, block IDs, tags, and common Markdown link noise before submitting.
- Use `--include-linked-notes` only when Luca wants one-hop wikilink context included. Review preview warnings for unresolved links.
- For PDFs, DOCX, or web clippings, reduce each source to clean text before submitting.
- Do not include secrets, API tokens, or private credentials inside source content.
- If a document is too large, the helper splits it into chunks with titles such as `Roadmap - Part 1`.
- If preview produces more than 20 sources after splitting and linked-note expansion, narrow the selection before submitting.
- If the episode remains in `generating_script` or `generating_audio`, continue polling at a reasonable interval instead of retrying immediately.
- If the episode fails, fetch the episode detail and report the exact `error_message`.
