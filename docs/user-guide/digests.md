# Digests

Digests are Ghostwriter's main output: a curated EPUB built from the content you ingest.

## How Digests Fit Into the Workflow

1. Ghostwriter fetches new content from feeds and integrations.
2. Articles are processed according to your configuration.
3. A digest is generated and stored.
4. You read it in the web UI, on mobile, or on an EPUB reader.

## First Digest Strategy

For your initial tests:

- use a small feed set
- run a manual digest
- inspect the resulting EPUB before enabling heavier automation

This helps separate content problems from scheduling problems.

## Common Digest Actions

- Trigger a digest manually for immediate feedback
- Review digest history after scheduled runs
- Download EPUB files for offline reading
- Sync completed digests to connected devices

## What to Check After a Run

- Did all expected feeds contribute content?
- Is article volume reasonable?
- Did the digest finish successfully?
- Does the EPUB render correctly in your preferred reader?

If the digest fails or comes out empty, start with [Startup and health checks](../troubleshooting/startup-and-health-checks.md) and [AI provider issues](../troubleshooting/ai-provider-issues.md).

## Related Pages

- [First digest walkthrough](../getting-started/first-digest.md)
- [Feeds](feeds.md)
- [Podcast generation](podcast-generation.md)
