# Aggregate backend feed compatibility correction

Base: aggregate PR119 `0987f80d4b16973cb00212545d5de6bb849e4369`.

PR119 comments [4116909634](https://github.com/LucaKaufmann/Ghostwriter/pull/119#discussion_r4116909634) and [4116909636](https://github.com/LucaKaufmann/Ghostwriter/pull/119#discussion_r4116909636) identify two independent compatibility problems. An existing feed's URL is immutable during web PUT, so metadata edits no longer perform DNS admission for that stored URL. The versioned write still enforces `If-Match`, and feed creation/fetch keep their URL and network safety checks. Bindery projects a persisted legacy feed cap through `readable_article_limit` when passing it to `ContentProcessor.parse_feed`: negative becomes 0 (unlimited), oversized becomes the native Int32 maximum. The raw database row remains untouched, and direct negative parser input remains invalid.

Focused fixtures cover metadata PUT while DNS fails plus stale-version conflict; actual bindery feed parsing from persisted negative/oversized rows with three returned entries and unchanged raw caps; and the parser's strict direct-negative guard. Focused pytest: **4 passed**. Ruff on affected files reports only the existing FastAPI `B008` defaults and `UP045` annotation in `app/api/feeds.py`; no new violation. Full backend suite pending independent source review.

All network fetches in these fixtures are synthetic, with no providers or production data.
