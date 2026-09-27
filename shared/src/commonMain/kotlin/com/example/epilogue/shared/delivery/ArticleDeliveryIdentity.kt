package com.example.epilogue.shared.delivery

/** Article identity is deliberately independent of the exact stored feed URL key. */
sealed class ArticleIdentityResult {
    data class Valid(val normalizedUrl: String, val articleKey: String) : ArticleIdentityResult()
    data object Invalid : ArticleIdentityResult()
}

/** Public class so Android and the generated Swift framework can call the same implementation. */
class ArticleDeliveryIdentity {
    fun fromArticleLink(link: String?): ArticleIdentityResult {
        val normalized = normalizeArticleUrl(link) ?: return ArticleIdentityResult.Invalid
        return ArticleIdentityResult.Valid(normalized, sha256Hex(normalized.encodeToByteArray()))
    }
}

internal expect fun sha256Hex(bytes: ByteArray): String

internal fun normalizeArticleUrl(link: String?): String? {
    if (link.isNullOrEmpty() || !wellFormedUnicode(link) ||
        link.any { it.isWhitespace() || it.isISOControl() || it == '\\' }) return null
    val colon = link.indexOf(':')
    if (colon <= 0) return null
    val scheme = link.substring(0, colon).lowercase()
    if (scheme != "http" && scheme != "https") return null
    if (!link.startsWith("//", colon + 1)) return null

    val authorityStart = colon + 3
    val authorityEnd = link.indexOfAny(charArrayOf('/', '?', '#'), authorityStart)
        .let { if (it < 0) link.length else it }
    val authority = link.substring(authorityStart, authorityEnd)
    if (authority.isEmpty() || '@' in authority) return null

    val host: String
    val portText: String?
    if (authority.startsWith('[')) {
        val close = authority.indexOf(']')
        if (close < 0 || !validIpv6(authority.substring(1, close))) return null
        host = "[${authority.substring(1, close).lowercase()}]"
        val suffix = authority.substring(close + 1)
        if (suffix.isNotEmpty() && !suffix.startsWith(':')) return null
        portText = if (suffix.isEmpty()) null else suffix.substring(1)
    } else {
        if ('[' in authority || ']' in authority) return null
        val portSeparator = authority.indexOf(':')
        host = (if (portSeparator < 0) authority else authority.substring(0, portSeparator)).lowercase()
        if (!validDnsHost(host)) return null
        portText = if (portSeparator < 0) null else authority.substring(portSeparator + 1)
    }
    val port = if (portText == null) null else {
        if (portText.isEmpty() || portText.any { it !in '0'..'9' }) return null
        val significant = portText.trimStart('0')
        if (significant.length > 5) return null
        significant.toIntOrNull()?.takeIf { it in 1..65535 } ?: return null
    }

    val fragmentStart = link.indexOf('#', authorityEnd).let { if (it < 0) link.length else it }
    val queryStart = link.indexOf('?', authorityEnd).takeIf { it >= 0 && it < fragmentStart }
    val pathEnd = queryStart ?: fragmentStart
    val rawPath = link.substring(authorityEnd, pathEnd)
    if (rawPath.isNotEmpty() && !rawPath.startsWith('/')) return null
    val path = rawPath.ifEmpty { "/" }
    val query = if (queryStart == null) "" else link.substring(queryStart, fragmentStart)
    if (!validRawComponent(path) || !validRawComponent(query) ||
        !validRawComponent(link.substring(fragmentStart).removePrefix("#"))) return null
    val normalizedPort = if ((scheme == "http" && port == 80) || (scheme == "https" && port == 443)) ""
        else if (portText == null) "" else ":$portText"
    return "$scheme://$host$normalizedPort$path$query"
}

private fun validDnsHost(host: String): Boolean {
    if (host.isEmpty() || host.length > 253 || host.startsWith('.') || ".." in host) return false
    val labels = host.trimEnd('.').split('.')
    if (labels.size == 4 && labels.all { label -> label.all { it in '0'..'9' } } &&
        !validIpv4(host)) return false
    return labels.all { label ->
        label.isNotEmpty() && label.length <= 63 && label.first().isLetterOrDigit() &&
            label.last().isLetterOrDigit() && label.all { it.isLetterOrDigit() || it == '-' }
    }
}

private fun validRawComponent(value: String): Boolean {
    var index = 0
    while (index < value.length) {
        if (value[index] == '%') {
            if (index + 2 >= value.length || !value[index + 1].isHex() || !value[index + 2].isHex()) return false
            index += 3
        } else {
            val char = value[index]
            if (char.code < 128 && !char.isAsciiUriCharacter()) return false
            index++
        }
    }
    return true
}

private fun Char.isHex(): Boolean = this in '0'..'9' || this in 'a'..'f' || this in 'A'..'F'

private fun Char.isAsciiUriCharacter(): Boolean = isLetterOrDigit() ||
    this in "-._~!$&'()*+,;=:@/?"

private fun wellFormedUnicode(value: String): Boolean {
    var index = 0
    while (index < value.length) {
        val char = value[index]
        if (char.isHighSurrogate()) {
            if (index + 1 >= value.length || !value[index + 1].isLowSurrogate()) return false
            index += 2
        } else {
            if (char.isLowSurrogate()) return false
            index++
        }
    }
    return true
}

private fun validIpv6(address: String): Boolean {
    if (address.isEmpty() || '%' in address || ":::" in address || address.count { it == ':' } < 2) return false
    if ((address.startsWith(':') && !address.startsWith("::")) ||
        (address.endsWith(':') && !address.endsWith("::"))) return false
    val compression = address.indexOf("::")
    if (compression >= 0 && address.indexOf("::", compression + 2) >= 0) return false
    if (compression < 0 && (address.startsWith(':') || address.endsWith(':'))) return false
    val groups = address.split(':').filter { it.isNotEmpty() }
    val ipv4 = groups.lastOrNull()?.takeIf { '.' in it }
    if (ipv4 != null && !validIpv4(ipv4)) return false
    val hexGroups = if (ipv4 == null) groups else groups.dropLast(1)
    if (hexGroups.any { it.length !in 1..4 || it.any { digit -> !digit.isHex() } }) return false
    val width = hexGroups.size + if (ipv4 == null) 0 else 2
    return if (compression >= 0) width < 8 else width == 8
}

private fun validIpv4(address: String): Boolean {
    val octets = address.split('.')
    return octets.size == 4 && octets.all { octet ->
        octet.isNotEmpty() && octet.length <= 3 && octet.all { it in '0'..'9' } &&
            (octet.length == 1 || octet.first() != '0') && octet.toInt() <= 255
    }
}
