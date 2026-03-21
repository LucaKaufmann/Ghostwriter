# Feeds

Feeds are the raw input for Ghostwriter digests. A clean feed setup keeps digest quality high and makes troubleshooting much easier.

## Start Small

When you first configure the server:

- add a small number of feeds
- confirm each feed saves correctly
- generate one digest before importing a large library

This makes it easier to isolate bad URLs, noisy feeds, or AI processing problems.

## Feed Types

Ghostwriter is centered on RSS and Atom feed ingestion, and the backend also includes media-oriented handling for podcast and YouTube style sources.

For most new users, the best starting point is still a normal article feed.

## Practical Feed Guidelines

- Prefer feeds with full article metadata and stable links.
- Avoid adding too many high-volume feeds at once.
- Mix feed types carefully if you are also testing media or podcast workflows.
- Keep an eye on article limits so one source does not dominate the digest.

## Ongoing Maintenance

Review your feeds periodically and remove:

- dead feeds
- duplicate feeds
- feeds that consistently produce low-value output

If a feed saves but never produces useful content, test with another known-good source before changing multiple settings at once.

## Related Pages

- [Digests](digests.md)
- [Settings and schedules](settings-and-schedules.md)
- [Startup and health checks](../troubleshooting/startup-and-health-checks.md)
