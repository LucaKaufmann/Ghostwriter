package com.example.epilogue.service

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PromotionalContentFilterTest {

    private val filter = PromotionalContentFilter()

    @Test
    fun `detects promotional content from url segment`() {
        val result = filter.isPromotional(
            url = "https://example.com/deals/special",
            title = "Normal title",
            content = null
        )

        assertTrue(result.isPromotional)
    }

    @Test
    fun `detects promotional content from title pattern`() {
        val result = filter.isPromotional(
            url = "https://example.com/article",
            title = "Save $50 on headphones",
            content = null
        )

        assertTrue(result.isPromotional)
    }

    @Test
    fun `detects promotional content from content markers`() {
        val result = filter.isPromotional(
            url = "https://example.com/article",
            title = "Some article",
            content = "Use code SAVE20 for a discount code today"
        )

        assertTrue(result.isPromotional)
    }

    @Test
    fun `does not flag neutral content`() {
        val result = filter.isPromotional(
            url = "https://example.com/news",
            title = "Policy update announced",
            content = "This is a neutral news article with no promotional intent."
        )

        assertFalse(result.isPromotional)
    }
}
