package com.example.epilogue.di

import okhttp3.OkHttpClient
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertSame
import org.junit.Test

class GhostwriterApiFactoryTest {

    @Test
    fun `create normalizes base url and caches instances`() {
        val factory = GhostwriterApiFactory(OkHttpClient())

        val api1 = factory.create("https://example.com")
        val api2 = factory.create("https://example.com/")
        val api3 = factory.create("https://example.com/api")

        assertSame(api1, api2)
        assertSame(api1, api3)
    }

    @Test
    fun `clearCache forces new instance`() {
        val factory = GhostwriterApiFactory(OkHttpClient())

        val api1 = factory.create("https://example.com")
        factory.clearCache()
        val api2 = factory.create("https://example.com")

        assertNotSame(api1, api2)
    }
}
