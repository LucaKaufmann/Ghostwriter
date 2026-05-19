"""Tests for digest article eligibility filtering."""

from app.services.article_eligibility_filter import ArticleEligibilityFilter


def test_filters_sponsored_title() -> None:
    result = ArticleEligibilityFilter().check(
        url="https://example.com/news",
        title="Sponsored: A message from Example Co",
    )

    assert result.eligible is False
    assert result.reason == "sponsored_title"


def test_filters_deal_title() -> None:
    result = ArticleEligibilityFilter().check(
        url="https://example.com/gadgets",
        title="This tablet drops to $199 for today only",
    )

    assert result.eligible is False
    assert result.reason == "deal_title"


def test_filters_affiliate_url() -> None:
    result = ArticleEligibilityFilter().check(
        url="https://example.com/affiliate/best-keyboards",
        title="Best keyboards for writers",
    )

    assert result.eligible is False
    assert result.reason == "promotional_url"


def test_filters_native_ad_metadata() -> None:
    result = ArticleEligibilityFilter().check(
        url="https://example.com/story",
        title="A cloud migration story",
        tags=["Native Ad"],
        summary="Partner content about infrastructure tooling.",
    )

    assert result.eligible is False
    assert "promotional_tag" in (result.reason or "")


def test_keeps_incidental_sponsor_word() -> None:
    result = ArticleEligibilityFilter().check(
        url="https://example.com/sports/team-budget",
        title="New sponsor deal changes the economics of women's football",
        summary="The article examines media rights, stadium revenue, and sponsorship.",
    )

    assert result.eligible is True


def test_keeps_long_editorial_sponsored_by_mention() -> None:
    result = ArticleEligibilityFilter().check(
        url="https://example.com/sports/team-budget",
        title="How shirt sponsorship reshaped club finances",
        content=(
            "The club is sponsored by a large technology company, but the "
            "article focuses on audited revenue, media rights, and transfer "
            "policy. "
            + "Additional reporting detail. " * 80
        ),
    )

    assert result.eligible is True


def test_keeps_incidental_sale_word() -> None:
    result = ArticleEligibilityFilter().check(
        url="https://example.com/business/company-sale",
        title="Regulators review the sale of a regional bank",
        summary="The proposed sale follows a year of consolidation in the sector.",
    )

    assert result.eligible is True
