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
        description: HTTPS base URL for Ghostwriter without the /api suffix
        prompt: Ghostwriter base URL
      - key: ghostwriter.token_env
        description: Environment variable containing the Ghostwriter API token or JWT
        default: "GHOSTWRITER_TOKEN"
        prompt: Ghostwriter token environment variable
---

# Ghostwriter One-Off Podcast

Use this skill when the user asks to turn one or more documents, notes, article URLs, or research sources into a one-off Ghostwriter podcast episode.

## Requirements

- Ghostwriter endpoint: `<GHOSTWRITER_BASE_URL>/api/podcast/episodes/one-off`
- Authentication: `Authorization: Bearer <token>`
- Base URL source: prefer `$GHOSTWRITER_BASE_URL`, then `$GW_BASE`, then `--base-url`. Use HTTPS for remote hosts. The helper only allows plain HTTP for loopback hosts unless `--allow-insecure-http` is explicitly passed.
- Token source: prefer `$GHOSTWRITER_TOKEN`, then `$GW_TOKEN`, then a `--env-file` such as `~/.env`; do not ask the user to paste secrets into chat if an environment variable or env file can be used.
- Phase 1 accepts only:
  - `type: "url"` for reachable article URLs
  - `type: "text"` for pasted or extracted document text
- Limits: 1-20 sources, each text source under 120000 characters, each source should have at least about 80 characters of usable content.

## Workflow

1. Collect the requested source material.
2. For Obsidian notes, pass note/folder paths to the helper instead of manually copying Markdown.
3. Preview source counts and warnings before submitting when the request has multiple notes or linked-note expansion.
4. Create the episode with `scripts/create_one_off_podcast.py`.
5. Poll until status is `ready` or `failed`.
6. Download the audio when the user asked for a file or automation output.
7. Report the episode id, final status, source count, downloaded path, and feed/download URL if ready. If failed, report `error_message`.

## Helper Script

Use the bundled script whenever possible:

```bash
python3 skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py \
  --env-file ~/.env \
  --title "Project planning brief" \
  --brief "Explain the source documents, tradeoffs, and next actions." \
  --text-file "Project Notes=/path/to/project-notes.txt" \
  --url "https://example.com/article" \
  --download \
  --output /path/to/project-planning-brief.mp3
```

Obsidian preview workflow:

```bash
python3 skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py \
  --title "Project notes podcast" \
  --brief "Explain these notes as a concise conversational briefing." \
  --obsidian-note "/path/to/Vault/Project.md" \
  --obsidian-folder "/path/to/Vault/Projects/Project" \
  --include-linked-notes \
  --preview
```

Write a full submit-ready preview file only when needed:

```bash
python3 skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py \
  --title "Project notes podcast" \
  --brief "Explain these notes as a concise conversational briefing." \
  --obsidian-note "/path/to/Vault/Project.md" \
  --preview \
  --preview-output /tmp/project-podcast-preview.json
```

Submit from a full preview file:

```bash
python3 skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py \
  --env-file ~/.env \
  --source-json /tmp/project-podcast-preview.json \
  --download \
  --output /path/to/project-notes.mp3
```

Environment overrides:

```bash
export GHOSTWRITER_BASE_URL="https://ghostwriter.example.com"
export GHOSTWRITER_TOKEN="gw_..."
```

If using a `.env` file, pass it directly instead of relying on `source ~/.env`; sourced shell variables only reach Python if they are exported:

```bash
python3 skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py \
  --env-file ~/.env \
  --text-file "Note=/path/to/note.md" \
  --download
```

The script automatically reads `~/.env` when present, unless `--no-default-env-files` is passed. It does not automatically read `./.env`; pass project-local env files with `--env-file .env` so the destination for authenticated requests is explicit. CLI flags override exported environment variables, which override env-file values.

The script prints JSON. On creation it includes `episode_id`, `digest_ids`, and `status`. With `--poll`, it prints the final episode detail. With `--download` or `--output`, it polls until ready, saves the MP3, and adds `downloaded_path` to the final JSON.

Preview stdout includes the payload shape with text source content redacted plus `_preview` metadata with source counts, word counts, warnings, source origins, and content hashes. `--preview-output` writes the full submit-ready JSON to a private file and that file can be passed back with `--source-json`.

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

- Keep documents in user-provided order unless the user asks for a different structure.
- Prefer extracted text for private/local documents; Ghostwriter cannot fetch files from the user's machine.
- For Obsidian, prefer `--obsidian-note` and `--obsidian-folder`; the helper strips YAML frontmatter, comments, embeds, wikilinks, block IDs, tags, and common Markdown link noise before submitting.
- Use `--include-linked-notes` only when the user wants one-hop wikilink context included. Review preview warnings for unresolved links.
- For PDFs, DOCX, or web clippings, reduce each source to clean text before submitting.
- Do not include secrets, API tokens, or private credentials inside source content.
- If a document is too large, the helper splits it into chunks with titles such as `Roadmap - Part 1`.
- If preview produces more than 20 sources after splitting and linked-note expansion, narrow the selection before submitting.
- If the episode remains in `generating_script` or `generating_audio`, continue polling at a reasonable interval instead of retrying immediately.
- If the episode fails, fetch the episode detail and report the exact `error_message`.
