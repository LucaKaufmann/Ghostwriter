"""Article eligibility checks for digest inclusion."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ArticleEligibilityResult:
    """Result of checking whether an article should be included."""

    eligible: bool
    reason: str | None = None
    confidence: float = 0.0


class ArticleEligibilityFilter:
    """Detect high-confidence sponsored, ad, deal, and affiliate posts."""

    THRESHOLD = 0.75

    _URL_PATTERNS = (
        (re.compile(r"/(?:deals?|offers?|promos?|promotions?|sales?|discounts?|coupons?|sponsored|affiliate)(?:/|$|[?#])"), 0.8),
        (re.compile(r"[?&](?:tag|utm_content|utm_campaign)=(?:[^&]*)(?:deal|sponsor|promo|affiliate)", re.I), 0.45),
    )

    _STRONG_TITLE_PATTERNS = (
        re.compile(r"^\s*(?:sponsored|advertisement|ad|paid post|partner post|promoted)\s*[:\-|]", re.I),
        re.compile(r"\b(?:sponsored|paid|partner|promoted)\s+(?:post|story|content|message|article)\b", re.I),
        re.compile(r"\b(?:advertisement|advertorial|native ad)\b", re.I),
    )

    _DEAL_TITLE_PATTERNS = (
        re.compile(r"\b\d+\s*(?:%|percent)\s+off\b", re.I),
        re.compile(r"\b(?:is|are|now|just|only)\s*\$\d+", re.I),
        re.compile(r"\bfor\s+(?:just|only)\s*\$\d+", re.I),
        re.compile(r"\$\d+\s+(?:off|discount)\b", re.I),
        re.compile(r"\bsave\s+\$\d+", re.I),
        re.compile(r"\b(?:lowest|best|cheapest)\s+price\b", re.I),
        re.compile(r"\b(?:deal|deals|sale|promo)\s*(?:of the|alert|:)\b", re.I),
        re.compile(r"\b(?:flash|lightning)\s+sale\b", re.I),
        re.compile(r"\b(?:limited time|today only|ends soon)\b", re.I),
        re.compile(r"\b(?:black friday|cyber monday|prime day)\b", re.I),
        re.compile(r"\byou can (?:get|grab|snag|score).*\$\d+", re.I),
        re.compile(r"\bdrops to\s*\$\d+", re.I),
        re.compile(r"\bat (?:an|its) (?:all-time )?low(?:est)?\b", re.I),
    )

    _CONTENT_MARKERS = (
        ("elm:affiliate_link", 0.35),
        ('data-type="product-list"', 0.35),
        ("<core-commerce", 0.35),
        ("coupon code", 0.4),
        ("promo code", 0.4),
        ("discount code", 0.4),
        ("use code ", 0.35),
        ("for the latest tech deals", 0.45),
        ("affiliate link", 0.35),
    )

    _SPONSORED_BLOCK_PATTERNS = (
        re.compile(r"^\s*(?:sponsored|advertisement|ad|paid post|partner message|promoted)\s*[:\-|]", re.I),
        re.compile(r"\b(?:sponsored|presented|brought to you|paid for|promoted)\s+by\b", re.I),
        re.compile(r"\b(?:this post|this article|this story)\s+is\s+sponsored\b", re.I),
        re.compile(r"\b(?:advertisement|advertorial|native ad|partner content)\b", re.I),
    )

    def check(
        self,
        *,
        url: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        content: str | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        author: str | None = None,
        source: str | None = None,
    ) -> ArticleEligibilityResult:
        """Return whether a candidate is eligible for digest inclusion."""

        score = 0.0
        reasons: list[str] = []

        normalized_url = (url or "").lower()
        for pattern, weight in self._URL_PATTERNS:
            if pattern.search(normalized_url):
                score += weight
                reasons.append("promotional_url")
                break

        normalized_title = title or ""
        if any(pattern.search(normalized_title) for pattern in self._STRONG_TITLE_PATTERNS):
            score += 0.85
            reasons.append("sponsored_title")
        elif any(pattern.search(normalized_title) for pattern in self._DEAL_TITLE_PATTERNS):
            score += 0.8
            reasons.append("deal_title")

        normalized_tags = [tag.strip().lower() for tag in tags or [] if tag and tag.strip()]
        if any(
            tag in {
                "sponsored",
                "advertisement",
                "advertorial",
                "native ad",
                "partner content",
                "deals",
            }
            for tag in normalized_tags
        ):
            score += 0.8
            reasons.append("promotional_tag")

        metadata_text = " ".join(
            value for value in (summary, content, author, source) if value
        )
        compact_text = self._normalize_text(metadata_text)
        for marker, weight in self._CONTENT_MARKERS:
            if marker in compact_text:
                score += weight
                reasons.append("promotional_marker")
                break

        starts_with_promotional_label = any(
            pattern.match(compact_text) for pattern in self._SPONSORED_BLOCK_PATTERNS
        )
        if self.is_promotional_block_text(compact_text) and (
            len(compact_text) < 1200 or starts_with_promotional_label
        ):
            score += 0.75
            reasons.append("sponsored_content")

        confidence = min(score, 1.0)
        if confidence >= self.THRESHOLD:
            return ArticleEligibilityResult(
                eligible=False,
                reason="+".join(dict.fromkeys(reasons)) or "promotional",
                confidence=confidence,
            )

        return ArticleEligibilityResult(eligible=True, confidence=confidence)

    def check_extracted(
        self,
        *,
        url: str | None,
        title: str | None,
        content: str | None,
        author: str | None = None,
        source: str | None = None,
    ) -> ArticleEligibilityResult:
        """Check extracted article text after readability/trafilatura processing."""

        return self.check(
            url=url,
            title=title,
            content=content,
            author=author,
            source=source,
        )

    @classmethod
    def is_promotional_block_text(cls, text: str | None) -> bool:
        """Return true for text blocks that are clearly sponsorship/ad labels."""

        if not text:
            return False
        value = cls._normalize_text(text)
        return any(pattern.search(value) for pattern in cls._SPONSORED_BLOCK_PATTERNS)

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip().lower()
