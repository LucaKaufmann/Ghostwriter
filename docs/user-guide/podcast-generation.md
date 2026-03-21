# Podcast Generation

Ghostwriter can turn completed digests into optional AI-narrated podcast episodes.

## What This Feature Does

Podcast generation adds a listening workflow on top of the normal digest pipeline:

- digest content becomes a script input
- a podcast episode is generated
- episodes can be exposed through a podcast feed for podcast apps

## Before You Enable It

Make sure the basic digest workflow already works:

- feeds are syncing
- digests complete successfully
- your AI provider is configured correctly

If the base digest flow is unstable, podcast generation will be harder to debug.

## Operational Requirements

Depending on your setup, you may need:

- AI provider credentials for script generation
- ElevenLabs or another configured narration path for audio generation
- A public base URL if podcast apps outside your local network need to access the feed

## Recommended Rollout

1. Confirm EPUB digests work reliably.
2. Enable podcast generation for a small test set.
3. Validate one complete episode end to end.
4. Only then expose the podcast feed to your regular listening apps.

## Related Pages

- [Settings and schedules](settings-and-schedules.md)
- [Podcast apps](../integrations/podcast-apps.md)
- [AI provider issues](../troubleshooting/ai-provider-issues.md)
