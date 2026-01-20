package com.example.epilogue.data.remote.ghostwriter

import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Streaming

/**
 * Retrofit interface for Ghostwriter backend API.
 *
 * All endpoints except /health require authentication when API_KEY is configured
 * on the server. Pass the API key via Authorization header.
 */
interface GhostwriterApi {

    // ===== Health =====

    /**
     * Check server health and status.
     * Does not require authentication.
     */
    @GET("health")
    suspend fun getHealth(): Response<HealthResponse>

    // ===== Feeds =====

    /**
     * List all configured feeds.
     */
    @GET("feeds")
    suspend fun listFeeds(
        @Header("Authorization") authorization: String?
    ): Response<List<FeedResponse>>

    /**
     * Sync feeds from the client (additive merge).
     * Creates new feeds and updates existing ones.
     * Feeds not in the list are left unchanged.
     */
    @POST("feeds/sync")
    suspend fun syncFeeds(
        @Header("Authorization") authorization: String?,
        @Body feeds: List<FeedSyncRequest>
    ): Response<FeedSyncResponse>

    /**
     * Delete a feed by URL.
     * Performs a soft delete (sets is_active = false).
     * Uses URL since the app doesn't track backend UUIDs.
     */
    @DELETE("feeds/by-url/{feedUrl}")
    suspend fun deleteFeedByUrl(
        @Header("Authorization") authorization: String?,
        @Path("feedUrl", encoded = true) feedUrl: String
    ): Response<Unit>

    // ===== Digests =====

    /**
     * Trigger a digest generation.
     * Returns 409 Conflict if a job is already running.
     */
    @POST("digests/trigger")
    suspend fun triggerDigest(
        @Header("Authorization") authorization: String?,
        @Body request: DigestTriggerRequest
    ): Response<DigestTriggerResponse>

    /**
     * List available digests.
     */
    @GET("digests")
    suspend fun listDigests(
        @Header("Authorization") authorization: String?
    ): Response<List<DigestResponse>>

    /**
     * Get the most recent completed digest.
     */
    @GET("digests/latest")
    suspend fun getLatestDigest(
        @Header("Authorization") authorization: String?
    ): Response<DigestResponse>

    /**
     * Get the status of a digest job (for polling progress).
     */
    @GET("digests/{digestId}/status")
    suspend fun getDigestStatus(
        @Header("Authorization") authorization: String?,
        @Path("digestId") digestId: String
    ): Response<DigestStatusResponse>

    /**
     * Download a digest EPUB file.
     */
    @Streaming
    @GET("digests/{filename}")
    suspend fun downloadDigest(
        @Header("Authorization") authorization: String?,
        @Path("filename") filename: String
    ): Response<ResponseBody>
}
