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

The script automatically reads `~/.env` when present, unless `--no-default-env-files` is passed. This handles the common case where `source ~/.env` appears to load values but Python cannot see them because the variables were not exported in the parent shell. It does not automatically read `./.env`; pass project-local env files with `--env-file .env` so the destination for authenticated requests is explicit. CLI flags override exported environment variables, which override env-file values.

Source title format: `--text-file "Title with spaces=/abs/path/to/file.md"` uses the text before `=` as the Ghostwriter source title. If you omit `=`, the filename is used.

Use the bundled script whenever possible:

```bash
python3 skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py \
  --env-file ~/.env \
  --title "Project planning brief" \
  --brief "Explain the source documents, tradeoffs, and next actions." \
  --voice-preset openai-balanced \
  --text-file "Project Notes=/path/to/project-notes.txt" \
  --url "https://example.com/article" \
  --save-response /path/to/project-planning-brief-response.json \
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
  --obsidian-include "*.md" \
  --obsidian-exclude "Archive/*" \
  --obsidian-tag research \
  --include-linked-notes \
  --linked-note-depth 2 \
  --include-backlinks \
  --source-manifest /tmp/project-podcast-manifest.json \
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
  --research-briefing \
  --voice-preset elevenlabs-research \
  --save-response /path/to/project-notes-response.json \
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

The script prints JSON. On creation it includes `episode_id`, `digest_ids`, and `status`. With `--poll`, it prints the final episode detail. With `--download` or `--output`, it polls until ready, saves the MP3, and adds `downloaded_path` to the final JSON. Use `--save-response PATH` to write the final response JSON, including the transcript when returned, to a private file. `--save-transcript PATH` is accepted as an alias for agents that think in transcript-retention terms. Use `--quiet` for automation that should print only one concise status line.

Preview stdout includes the payload shape with text source content redacted plus `_preview` metadata with source counts, word counts, estimated source minutes, estimated TTS characters, warnings, source origins, tags, and content hashes. `--preview-output` writes the full submit-ready JSON to a private file and that file can be passed back with `--source-json`. `--source-manifest PATH` writes only the redaction-safe `_preview` metadata to a private JSON file for audit trails.

Generation override flags:

- `--voice-preset`: one of `openai-balanced`, `openai-energetic`, `openai-solo-analysis`, `elevenlabs-research`, or `elevenlabs-formal`.
- `--tts-provider`: `openai` or `elevenlabs`.
- `--host-count`: `1` for solo narration or `2` for a host dialogue.
- `--host-a-voice` / `--host-b-voice`: provider voice name/ID. For ElevenLabs use voice IDs.
- `--style`: `casual`, `formal`, or `deep-dive`.
- `--preferred-length-minutes`, `--script-model`, and `--script-timeout-seconds`: per-episode generation preferences.
- `--research-briefing`: appends guidance for AI-agent research notes, emphasizing evidence, uncertainty, contradictions, decisions, and next actions.

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

Optional per-episode generation overrides are accepted under `generation`:

```json
{
  "generation": {
    "tts_provider": "elevenlabs",
    "host_count": 2,
    "host_a_voice": "iP95p4xoKVk53GoZ742B",
    "host_b_voice": "XrExE9yKIg1WjnnlVkGX",
    "style": "deep-dive",
    "preferred_length_minutes": 12
  }
}
```

## Voice Catalog

Ghostwriter exposes the shared catalog at `/api/podcast/voices`. Use these IDs in one-off `generation` overrides or helper flags.

| Provider | Name | ID | Vibe | Best suited for |
| --- | --- | --- | --- | --- |
| OpenAI | Alloy | `alloy` | Balanced, neutral, clear | General research briefings and mixed-source summaries |
| OpenAI | Echo | `echo` | Warm, conversational, steady | Context-setting, explanatory turns, and recaps |
| OpenAI | Fable | `fable` | Expressive, story-forward, lighter | Narrative explainers and approachable solo summaries |
| OpenAI | Onyx | `onyx` | Deep, calm, authoritative | Serious analysis, longer-form synthesis, and solo narration |
| OpenAI | Nova | `nova` | Bright, quick, energetic | Hooks, momentum, and lively research updates |
| OpenAI | Shimmer | `shimmer` | Polished, friendly, precise | Executive-style briefings and concise summaries |
| ElevenLabs | Chris | `iP95p4xoKVk53GoZ742B` | Natural, confident, presenter-like | Host A in research briefings and decision summaries |
| ElevenLabs | Matilda | `XrExE9yKIg1WjnnlVkGX` | Warm, clear, explanatory | Host B context, definitions, and clarifying questions |
| ElevenLabs | George | `JBFqnCBsd6RMkjVDRZzb` | Measured, grounded, direct | Formal analysis and slower-paced synthesis |
| ElevenLabs | Bella | `hpp4J3VqNfWAUOO0d1Us` | Friendly, responsive, conversational | Accessible companion host and lighter recap segments |

Useful pairings:

- `Alloy + Echo`: balanced OpenAI research briefing.
- `Nova + Fable`: more energetic narrative episode.
- `Chris + Matilda`: default ElevenLabs research briefing.
- `George + Bella`: formal analysis with warmer companion context.

## Operating Rules

- Keep documents in user-provided order unless the user asks for a different structure.
- Prefer extracted text for private/local documents; Ghostwriter cannot fetch files from the user's machine.
- For Obsidian, prefer `--obsidian-note` and `--obsidian-folder`; the helper strips YAML frontmatter, comments, embeds, wikilinks, block IDs, tags, and common Markdown link noise before submitting.
- Use `--include-linked-notes` only when the user wants wikilink context included. Keep `--linked-note-depth` bounded and review preview warnings for unresolved links.
- For PDFs, DOCX, or web clippings, reduce each source to clean text before submitting.
- Do not include secrets, API tokens, or private credentials inside source content.
- For wiki or research use cases, persist the Ghostwriter response with `--save-response` so the generated synthesis remains auditable separately from verbatim source material.
- If a document is too large, the helper splits it into chunks with titles such as `Roadmap - Part 1`.
- If preview produces more than 20 sources after splitting and linked-note expansion, narrow the selection before submitting.
- If the episode remains in `generating_script` or `generating_audio`, continue polling at a reasonable interval instead of retrying immediately.
- If the episode fails, fetch the episode detail and report the exact `error_message`.
