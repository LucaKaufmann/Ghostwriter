# FETCH-01 result

Base: `de68d540ea67383a3843b8085659d29dcf19baaa` (ENV-01 integration). Branch: `codex/fetch-01-bounded-requests`. Head and PR are reported to the orchestrator after acceptance.

## Behavior

RSS and article extraction now use the same bounded HTTP fetch path as reader documents: automatic redirects disabled, each destination validated before transport, finite redirect count and total deadline, encoded and decoded byte caps, and separate feed XML versus HTML MIME checks. The fetch helper advertises identity/gzip and limits gzip expansion during decompression; unsupported content encodings fail cleanly. URL validation runs off the event loop within the total deadline, and its expiry raises `httpx.ReadTimeout` for the reader endpoint's existing 504 mapping. Feed requests preserve feedparser's RSS/Atom/XML Accept header. Feedparser receives bytes with the final URL as `Content-Location`; relative article and enclosure links resolve against it. Trafilatura receives the fetched bytes and final URL. Reader return type, decoding and exception imports remain compatible. Explicit `allow_private_hosts` remains available. DNS lookup failures from URL validation now raise `ValueError("Hostname could not be resolved")` without echoing resolver details.

## Verification

- Runtime: Python 3.11.16; Ruff 0.16.9, using the read-only ENV-01 virtual environment. Tests ran from this branch's `ghostwriter/` directory under ENV-01's blocked-network fixture.
- `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv/bin/python -m pytest -q tests/test_content_processor.py tests/test_reader_service.py tests/test_outbound_fetch.py tests/test_media_processor.py tests/test_podcast_api.py` — 143 passed, 2 existing dependency warnings.
- `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv/bin/python -m ruff check app/core/net.py app/services/content_processor.py app/services/reader_service.py app/services/outbound_fetch.py tests/test_content_processor.py tests/test_reader_service.py tests/test_outbound_fetch.py` — all checks passed.
- `git diff --check` — passed.

Transport/resolver tests use only mocked responses and fixture addresses. No real provider, private host, or production content was contacted.

Independent Sol review found four issues in the first commit: decoded gzip bytes could exceed the cap before checking, synchronous DNS could outlast the deadline and block the event loop, total deadline expiry bypassed the reader's 504 mapping, and RSS requests lost their feed-specific Accept header. This revision addresses all four with focused regression tests; final independent review remains with the orchestrator.

## Limits and next action

URL validation and HTTP connection each resolve DNS. This change does **not** pin the validated IP address for the connection, so a resolver change between the two steps remains possible. Address pinning would need a separate small, tested transport design that preserves Host and TLS validation. The reader's previous guard had the same gap. The helper also does not change other outbound paths such as media downloads. Independent security review and integrated-base acceptance belong to the orchestrator; no merge or deployment occurred.
