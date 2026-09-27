package com.example.epilogue.shared.delivery

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class ArticleDeliveryIdentityTest {
    private val identity = ArticleDeliveryIdentity()

    @Test
    fun canonicalStringsAndIndependentSha256Vectors() {
        // SHA-256 values generated with Python hashlib, independent of either platform actual.
        val vectors = listOf(
            Triple("HTTPS://EXAMPLE.COM:443#section", "https://example.com/", "0f115db062b7c0dd030b16878c99dea5c354b49dc37b38eb8846179c7783e9d7"),
            Triple("HTTP://Example.Com:80/Case/%2f%2F?a=1&a=2&z=%7e&b=%2B#f", "http://example.com/Case/%2f%2F?a=1&a=2&z=%7e&b=%2B", "8da1383570b252ff2b08f0df3947f9ff030aeeb5a441fd5a45f9ab39e9e111f2"),
            Triple("https://[2001:DB8::1]:443/A?x=1", "https://[2001:db8::1]/A?x=1", "4d2e7bf3be0c55e0fae50d35dac69a4f378d65e3f7a7cc26c5723bbb22953a77"),
            Triple("https://EXAMPLE.com?#fragment", "https://example.com/?", "d5551a1c99bf9012cf47d1344c69fb4b8a36b6be858e683a4d0945eaac82c224"),
            Triple("https://BÜCHER.example/Über?q=café", "https://bücher.example/Über?q=café", "fcffd07e6f0325f457b2048f14cd9c5011b723e8a20ff13c58bcdacdfb870a78"),
            Triple("http://EXAMPLE.COM:8080/a", "http://example.com:8080/a", "a646557523c82ace727c663e903a52a390842b173745f0ecc68e1b750d768ca7"),
            Triple("https://EXAMPLE.com:000443/a", "https://example.com/a", "2dce0a4c50441bfccfa9caf4b58c3cba6e06c420505dd829f0436de1aa44baac"),
            Triple("http://[::FFFF:192.0.2.1]/a", "http://[::ffff:192.0.2.1]/a", "c7c210217266695da4b97da46ba6459b7c97b5b019fa336f5cba66e655c9cdf0"),
            Triple("http://192.0.2.1./a", "http://192.0.2.1./a", "a2f6797e6fc684f1ec1d1bb5cc6a530fb7162e9b50adfdf269a468079457caef"),
        )
        vectors.forEach { (input, normalized, hash) ->
            val actual = assertIs<ArticleIdentityResult.Valid>(identity.fromArticleLink(input), input)
            assertEquals(normalized, actual.normalizedUrl, input)
            assertEquals(hash, actual.articleKey, input)
        }
    }

    @Test
    fun invalidLinksHaveNoIdentity() {
        listOf<String?>(
            null, "", "example.com/a", "/relative", "ftp://example.com/a",
            "https://user@example.com/a", "https://user:pass@example.com/a",
            "http://example.com:bad/a", "http://example.com:65536/a", "http://example.com:/a",
            "http://example.com:0/a", "http://[2001:db8::1/a", "http://[1:::2]/a",
            "http://[:1::2]/a", "http://[1::2:]/a", "http://[::ffff:192.0.2.1:]/a",
            "http://[1:2:192.0.2.1::]/a",
            "https://example.com/%GG", "https://example.com/a b", "http://example.com\\a",
            "https://example.com/<bad>", "https://example.com/\uD800", "https://example.com/\uDC00",
            "http:///missing-host", "https://example..com/",
        ).forEach { input -> assertEquals(ArticleIdentityResult.Invalid, identity.fromArticleLink(input), input) }
    }
}
