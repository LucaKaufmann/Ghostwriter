# FETCH-01 result

Base: `de68d540ea67383a3843b8085659d29dcf19baaa` (ENV-01 integration). Branch: `codex/fetch-01-bounded-requests`. Head and PR are reported to the orchestrator after acceptance.

## Behavior

RSS and article extraction now use the same bounded HTTP fetch path as reader documents: automatic redirects disabled, each destination validated before transport, finite redirect count and total deadline, encoded and decoded byte caps, and separate feed XML versus HTML MIME checks. The fetch helper advertises identity/gzip and limits gzip expansion during decompression; malformed or unsupported content encodings raise an HTTPX decoding error so reader stored-content fallback remains available. URL validation runs in a dedicated four-worker pool within the total deadline. An expired lookup keeps its admission slot until the OS call finishes, preventing unlimited queued DNS work; callers wait for capacity within the total fetch deadline instead of dropping healthy concurrent fetches. Total deadline expiry raises `httpx.ReadTimeout` for the reader endpoint's existing 504 mapping. HTTPX keeps its environment proxy and CA behavior. Feed requests preserve feedparser's RSS/Atom/XML Accept header. Feedparser receives bytes with the upstream `Content-Location` resolved against the final response URL, or that URL as a fallback for missing/malformed headers; relative article and enclosure links use the same base. Trafilatura receives the fetched bytes and final URL. Reader return type, decoding and exception imports remain compatible. Explicit `allow_private_hosts` remains available. DNS lookup failures from URL validation now raise `ValueError("Hostname could not be resolved")` without echoing resolver details.

## Verification

- Runtime: Python 3.11.16; Ruff 0.16.9, using the read-only ENV-01 virtual environment. Tests ran from this branch's `ghostwriter/` directory under ENV-01's blocked-network fixture.
- `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv/bin/python -m pytest -q tests/test_content_processor.py tests/test_reader_service.py tests/test_outbound_fetch.py tests/test_media_processor.py tests/test_podcast_api.py` — 152 passed, 2 existing dependency warnings.
- `/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv/bin/python -m ruff check app/core/net.py app/services/content_processor.py app/services/reader_service.py app/services/outbound_fetch.py tests/test_content_processor.py tests/test_reader_service.py tests/test_outbound_fetch.py` — all checks passed.
- `git diff --check` — passed.

Transport/resolver tests use only mocked responses and fixture addresses. No real provider, private host, or production content was contacted.

Independent Sol review found four issues in the first commit: decoded gzip bytes could exceed the cap before checking, synchronous DNS could outlast the deadline and block the event loop, total deadline expiry bypassed the reader's 504 mapping, and RSS requests lost their feed-specific Accept header. This revision addresses all four with focused regression tests; final independent review remains with the orchestrator.

The next Sol review found four compatibility and capacity issues: decoding errors took the URL-validation response path, upstream `Content-Location` was lost, timed-out DNS calls could fill the shared worker pool, and HTTPX environment proxy/CA settings were disabled. The current revision corrects these with offline fallback, base-URL, worker saturation/recovery, and environment-option tests.

The final compatibility review identified eager DNS-capacity rejection and malformed optional Content-Location. Admission now waits on worker-completion notifications inside the deadline with the same bounded worker count, without periodic polling; invalid header syntax falls back to the final URL. Eight simultaneous healthy fetches, timed-out saturation/recovery, and malformed feed/HTML headers have regression coverage.

## Limits and next action

URL validation and HTTP connection each resolve DNS. This change does **not** pin the validated IP address for the connection, so a resolver change between the two steps remains possible; configured proxies may also resolve separately. Address pinning would need a separate small, tested transport design that preserves Host and TLS validation. The reader's previous guard had the same gap. A timed-out OS DNS call cannot be cancelled, but at most four validator calls can occupy the isolated pool. The helper also does not change other outbound paths such as media downloads. Final targeted Sol review of the event-driven admission correction is clean after the prior full reviews. Combined-base verification remains with the orchestrator; no merge or deployment occurred.
