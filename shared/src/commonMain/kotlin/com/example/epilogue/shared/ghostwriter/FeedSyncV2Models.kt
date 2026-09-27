package com.example.epilogue.shared.ghostwriter

import com.example.epilogue.shared.delivery.normalizeArticleUrl
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

const val MAX_FEED_VERSION_V2: Long = 9_007_199_254_740_991L

@Serializable
data class FeedSnapshotV2(
    val kind: String,
    val id: String,
    val url: String,
    val version: Long,
    val title: String? = null,
    @SerialName("is_active") val isActive: Boolean? = null,
    val mode: String? = null,
    @SerialName("max_articles") val maxArticles: Int? = null
)

@Serializable
data class FeedChangesV2Response(
    @SerialName("server_instance_id") val serverInstanceId: String,
    @SerialName("server_version") val serverVersion: Long,
    val changes: List<FeedSnapshotV2>
)

@Serializable
data class FeedDirtyFieldsV2(
    val title: String? = null,
    @SerialName("is_active") val isActive: Boolean? = null,
    val mode: String? = null,
    @SerialName("max_articles") val maxArticles: Int? = null
) {
    fun isEmpty(): Boolean = title == null && isActive == null && mode == null && maxArticles == null
    fun isComplete(): Boolean = title != null && isActive != null && mode != null && maxArticles != null
    fun isValid(): Boolean = !isEmpty() && (mode == null || mode == "raw" || mode == "summarize") &&
        (maxArticles == null || maxArticles >= 0)
}

@Serializable
data class FeedMutationV2(
    @SerialName("op_id") val opId: String,
    val url: String,
    val kind: String,
    @SerialName("base_version") val baseVersion: Long?,
    val fields: FeedDirtyFieldsV2? = null
)

@Serializable
data class FeedMutationBatchV2(
    @SerialName("server_instance_id") val serverInstanceId: String,
    val mutations: List<FeedMutationV2>
)

@Serializable
data class FeedMutationResultV2(
    @SerialName("op_id") val opId: String,
    val status: String,
    val current: FeedSnapshotV2? = null,
    val code: String? = null,
    val message: String? = null
)

@Serializable
data class FeedMutationBatchResultV2(
    @SerialName("server_instance_id") val serverInstanceId: String,
    val results: List<FeedMutationResultV2>
)

/** Explicit null base_version is required; optional fields are omitted, including on delete. */
val feedV2Json = Json { ignoreUnknownKeys = true }

fun FeedMutationBatchV2.toWireJson(): String {
    require(isUuidV2(serverInstanceId) && mutations.size <= 100)
    require(mutations.map { canonicalUuidV2(it.opId) }.distinct().size == mutations.size)
    mutations.forEach { mutation ->
        require(isUuidV2(mutation.opId) && isFeedUrlV2(mutation.url))
        require(mutation.baseVersion == null || validVersionV2(mutation.baseVersion))
        require(if (mutation.kind == "delete") mutation.fields == null else
            mutation.kind == "upsert" && mutation.fields?.isValid() == true &&
                (mutation.baseVersion != null || mutation.fields.isComplete()))
    }
    return feedV2Json.encodeToString(this)
}

fun validVersionV2(version: Long): Boolean = version in 0..MAX_FEED_VERSION_V2

fun isFeedUrlV2(url: String): Boolean {
    val separator = url.indexOf("://")
    if (separator < 0 || url.substring(0, separator).lowercase() !in listOf("http", "https")) return false
    val authority = url.substring(separator + 3).substringBefore('/').substringBefore('?').substringBefore('#')
    return authority.isNotBlank() && '@' !in authority && authority.none { it.isWhitespace() }
}

/** New local admission only. Validation never replaces the URL used as the feed key. */
fun isAdmissibleNewFeedUrlV2(url: String): Boolean = normalizeArticleUrl(url) != null

fun isUuidV2(value: String): Boolean = value.length == 36 && value.indices.all { index ->
    when (index) {
        8, 13, 18, 23 -> value[index] == '-'
        else -> value[index] in '0'..'9' || value[index] in 'a'..'f' || value[index] in 'A'..'F'
    }
}

/** Compare UUID identity canonically; never rewrite an already-sent payload or receipt key. */
fun canonicalUuidV2(value: String): String? = if (isUuidV2(value)) value.lowercase() else null

fun FeedSnapshotV2.isValidV2(): Boolean = isUuidV2(id) && isFeedUrlV2(url) &&
    validVersionV2(version) && when (kind) {
        "feed" -> title != null && isActive != null && mode in listOf("raw", "summarize") &&
            maxArticles != null && maxArticles >= 0
        "tombstone" -> title == null && isActive == null && mode == null && maxArticles == null
        else -> false
    }

fun FeedChangesV2Response.isValidV2(full: Boolean, sinceVersion: Long?): Boolean =
    isUuidV2(serverInstanceId) && validVersionV2(serverVersion) &&
        (full || sinceVersion != null) && changes.all { it.isValidV2() && it.version <= serverVersion &&
            (full || it.version > sinceVersion!!) } &&
        changes.map { it.url }.distinct().size == changes.size &&
        changes.zipWithNext().all { (a, b) -> a.version < b.version }
