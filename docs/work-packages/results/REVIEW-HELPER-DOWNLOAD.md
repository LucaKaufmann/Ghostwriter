# REVIEW-HELPER-DOWNLOAD result

The one-off podcast helper previously passed the episode's advertised `download_url` to its authenticated transport. When Ghostwriter advertised `PODCAST_PUBLIC_BASE_URL` on a different origin from the configured API address, the transport correctly rejected the request, but `--download` could not fetch the ready episode.

The helper now validates the advertised URL's syntax without requesting it, canonicalizes the episode's UUID, and downloads from the backend's authenticated `/api/podcast/episodes/{episode_id}/download` route on the configured API origin. The canonical UUID is also used for polling and the default MP3 filename. The authenticated transport still rejects off-origin redirects and non-loopback HTTP without explicit opt-in. No backend route, authentication rule, or public URL generation changed.

Verification: Python 3.11 `python -m unittest discover -s skills/ghostwriter-one-off-podcast/tests -p 'test_transport.py' -v` passed **20/20**. Synthetic HTTP fixtures cover internal/public and same-origin advertised URLs, malformed IDs and URLs, canonical hex UUIDs, default filename, redirect credential isolation, explicit HTTP opt-in, and the existing direct transport rejection cases. `ruff check` on both changed Python files and `git diff --check` passed. No real network or provider request was made.

The helper still requires a syntactically valid advertised URL in the episode response, even though it does not follow that URL. A missing or malformed URL remains an episode response error.
