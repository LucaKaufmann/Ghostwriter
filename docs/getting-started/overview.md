# Getting Started Overview

Ghostwriter works best when you treat setup as a short sequence:

1. Install and start the Ghostwriter server.
2. Create the first admin account in the web UI.
3. Generate API tokens for mobile clients or reader integrations.
4. Add feeds and produce your first digest.

## Recommended First-Run Path

Follow these pages in order:

1. [Ghostwriter Docker installation](../installation/ghostwriter-docker.md)
2. [Self-hosted quick start](self-hosted-quickstart.md)
3. [Connect mobile apps](connect-mobile-apps.md)
4. [First digest walkthrough](first-digest.md)

## What You Need

- Docker and Docker Compose for the supported self-hosted path
- An AI provider configured for briefing features:
  - OpenAI
  - Google Gemini
  - Ollama for local models
- A browser to access the Ghostwriter web UI
- Optional:
  - iPhone, iPad, or Android device
  - KOReader or another EPUB-capable reader
  - ElevenLabs if you want narrated podcast episodes

## System Components

- **Ghostwriter**: runs feed sync, digest generation, scheduling, the web UI, and optional podcast generation
- **Epilogue mobile apps**: connect to Ghostwriter with API tokens and consume digests
- **Reader integrations**: pull EPUBs into KOReader or other reading workflows

## Choose the Right Install Path

- Use [Ghostwriter with Docker](../installation/ghostwriter-docker.md) for the main supported deployment.
- Use [Ghostwriter from source](../installation/ghostwriter-local.md) if you are evaluating locally or developing.
- Review [iOS availability](../installation/ios.md) or [Android availability](../installation/android.md) before planning a mobile rollout.

## Next Step

Continue with [Self-hosted quick start](self-hosted-quickstart.md).
