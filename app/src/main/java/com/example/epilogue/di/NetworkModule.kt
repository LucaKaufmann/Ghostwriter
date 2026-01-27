package com.example.epilogue.di

import com.example.epilogue.data.remote.ghostwriter.GhostwriterApi
import com.example.epilogue.data.repository.SettingsRepository
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideOkHttpClient(): OkHttpClient {
        val loggingInterceptor = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }

        return OkHttpClient.Builder()
            .connectTimeout(60, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(60, TimeUnit.SECONDS)
            .addInterceptor(loggingInterceptor)
            .build()
    }

    /**
     * Provides a GhostwriterApiFactory that creates GhostwriterApi instances
     * with the configured base URL. This allows dynamic URL configuration.
     */
    @Provides
    @Singleton
    fun provideGhostwriterApiFactory(
        okHttpClient: OkHttpClient
    ): GhostwriterApiFactory {
        return GhostwriterApiFactory(okHttpClient)
    }
}

/**
 * Factory for creating GhostwriterApi instances with dynamic base URLs.
 * This is needed because the Ghostwriter URL is user-configurable.
 */
class GhostwriterApiFactory(
    private val okHttpClient: OkHttpClient
) {
    private var cachedApi: GhostwriterApi? = null
    private var cachedBaseUrl: String? = null

    /**
     * Creates or returns a cached GhostwriterApi for the given base URL.
     */
    fun create(baseUrl: String): GhostwriterApi {
        // Normalize URL
        val normalizedUrl = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"

        // Return cached instance if URL hasn't changed
        if (cachedApi != null && cachedBaseUrl == normalizedUrl) {
            return cachedApi!!
        }

        // Create new instance
        val retrofit = Retrofit.Builder()
            .baseUrl(normalizedUrl)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()

        cachedApi = retrofit.create(GhostwriterApi::class.java)
        cachedBaseUrl = normalizedUrl

        return cachedApi!!
    }

    /**
     * Clears the cached API instance (call when URL changes).
     */
    fun clearCache() {
        cachedApi = null
        cachedBaseUrl = null
    }
}
