package com.example.epilogue.shared.ghostwriter

import com.example.epilogue.shared.sync.FeedV2Destination
import com.example.epilogue.shared.sync.FeedV2RemoteResult
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.http.content.TextContent
import io.ktor.serialization.kotlinx.json.json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class FeedSyncV2TransportTest {
    private val instance = "21410e08-44a1-4944-8910-5a74c39a7271"
    private val op = "3e1a59a5-f547-40b2-9a6b-4c54e80a03dc"
    private val destination = FeedV2Destination("http://localhost:8080", "config-1")

    @Test
    fun firstAndBoundPullUseExactRouteAndParameters() = runTest {
        val urls = mutableListOf<String>()
        val client = client { request ->
            urls += request.url.toString()
            """{"server_instance_id":"$instance","server_version":0,"changes":[]}""" to HttpStatusCode.OK
        }
        assertIs<FeedV2RemoteResult.Success<FeedChangesV2Response>>(
            client.second.getFeedChangesV2(destination, null, null))
        assertIs<FeedV2RemoteResult.Success<FeedChangesV2Response>>(
            client.second.getFeedChangesV2(destination, 0, instance))
        assertEquals("http://localhost:8080/api/feeds/changes-v2", urls[0])
        assertTrue(urls[1].contains("since_version=0"))
        assertTrue(urls[1].contains("server_instance_id=$instance"))
        client.first.close()
    }

    @Test
    fun requestHasExplicitNullBaseOnlyDirtyFieldsAndZeroCap() = runTest {
        var body = ""
        val client = client { request ->
            body = (request.body as TextContent).text
            """{"server_instance_id":"$instance","results":[]}""" to HttpStatusCode.OK
        }
        val create = FeedMutationV2(op, "https://example.test/rss", "upsert", null,
            FeedDirtyFieldsV2("Title", true, "raw", 0))
        client.second.postFeedMutationsV2(destination, FeedMutationBatchV2(instance, listOf(create)))
        val createJson = Json.parseToJsonElement(body).jsonObject["mutations"]
        assertTrue(body.contains("\"base_version\":null"))
        assertTrue(body.contains("\"max_articles\":0"))
        assertTrue(createJson != null)
        val edit = FeedMutationV2(op, "https://example.test/rss", "upsert", 4,
            FeedDirtyFieldsV2(title = "Edited"))
        client.second.postFeedMutationsV2(destination, FeedMutationBatchV2(instance, listOf(edit)))
        assertFalse(body.contains("is_active"))
        assertFalse(body.contains("max_articles"))
        client.second.postFeedMutationsV2(destination, FeedMutationBatchV2(instance,
            listOf(FeedMutationV2(op, "https://example.test/rss", "delete", 4))))
        assertFalse(body.contains("fields"))
        client.first.close()
    }

    @Test
    fun fastApiDetailCodeAndDestinationArePreserved() = runTest {
        var requests = 0
        val client = client { _ ->
            requests++
            """{"detail":{"code":"server_changed"}}""" to HttpStatusCode.Conflict
        }
        val changed = client.second.getFeedChangesV2(destination, 4, instance)
        assertEquals("server_changed", assertIs<FeedV2RemoteResult.HttpFailure>(changed).code)
        val wrong = client.second.getFeedChangesV2(
            destination.copy(normalizedBaseUrl = "http://elsewhere"), 4, instance)
        assertIs<FeedV2RemoteResult.TransportFailure>(wrong)
        assertEquals(1, requests)
        client.first.close()
    }

    @Test
    fun uppercaseFrozenOpIsSentUnchangedAndCanonicalServerReceiptDecodes() = runTest {
        var body = ""
        val client = client { request ->
            body = (request.body as TextContent).text
            """{"server_instance_id":"$instance","results":[{"op_id":"$op","status":"applied","current":null}]}""" to
                HttpStatusCode.OK
        }
        val original = FeedMutationV2(op.uppercase(), "https://example.test/rss", "delete", null)
        val response = client.second.postFeedMutationsV2(destination,
            FeedMutationBatchV2(instance.uppercase(), listOf(original)))
        assertEquals(op, assertIs<FeedV2RemoteResult.Success<FeedMutationBatchResultV2>>(response)
            .value.results.single().opId)
        assertTrue(body.contains(op.uppercase()))
        assertTrue(body.contains(instance.uppercase()))
        assertEquals(body, FeedMutationBatchV2(instance.uppercase(), listOf(original)).toWireJson())
        client.first.close()
    }

    @Test
    fun writerRejectsOversizeAndInvalidFieldsBeforeNetwork() {
        val payload = FeedMutationV2(op, "https://example.test/rss", "upsert", 4,
            FeedDirtyFieldsV2(maxArticles = 0))
        assertTrue(FeedMutationBatchV2(instance, listOf(payload)).toWireJson().contains("\"max_articles\":0"))
        assertTrue(runCatching { FeedMutationBatchV2(instance, List(101) { payload }).toWireJson() }.isFailure)
        assertTrue(runCatching { FeedMutationBatchV2(instance, listOf(payload.copy(baseVersion = null))).toWireJson() }.isFailure)
        assertTrue(runCatching { FeedMutationBatchV2(instance, listOf(payload,
            payload.copy(opId = op.uppercase(), url = "https://example.test/other"))).toWireJson() }.isFailure)
    }

    @Test
    fun newAdmissionChecksHostAndPortWithoutChangingLegacyWireOrSnapshotShape() {
        listOf(
            "HTTPS://EXAMPLE.com:443/Case/%2f?x=1%2F2&x=%7e#part",
            "http://[2001:DB8::1]:8080/rss?tag=One%2FTwo",
            "https://bücher.example/Über?q=café"
        ).forEach { assertTrue(isAdmissibleNewFeedUrlV2(it), it) }
        listOf(
            "http://:8080/rss", "http:///rss", "http://example.com:/rss",
            "http://example.com:bad/rss", "http://example.com:0/rss",
            "http://example.com:65536/rss", "http://[2001:db8::1/rss",
            "https://user@example.com/rss", "https://example.com/%GG"
        ).forEach { assertFalse(isAdmissibleNewFeedUrlV2(it), it) }

        val legacy = "http://:8080/rss"
        assertTrue(isFeedUrlV2(legacy))
        assertTrue(FeedSnapshotV2("feed", op, legacy, 1, "Known", true, "raw", 0).isValidV2())
        val replay = FeedMutationBatchV2(instance, listOf(FeedMutationV2(
            op, legacy, "upsert", 1, FeedDirtyFieldsV2(title = "Edited"))))
        assertTrue(replay.toWireJson().contains("\"url\":\"$legacy\""))
    }

    private fun client(
        respondWith: (io.ktor.client.request.HttpRequestData) -> Pair<String, HttpStatusCode>
    ): Pair<HttpClient, GhostwriterApiClient> {
        val http = HttpClient(MockEngine { request ->
            val (body, status) = respondWith(request)
            respond(body, status, headersOf(HttpHeaders.ContentType, "application/json"))
        }) {
            install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
        }
        return http to GhostwriterApiClient(http, destination.normalizedBaseUrl, "test-token")
    }
}
