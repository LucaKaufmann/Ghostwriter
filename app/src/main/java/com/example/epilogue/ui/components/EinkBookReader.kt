package com.example.epilogue.ui.components

import android.graphics.Typeface
import android.text.Layout
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.StaticLayout
import android.text.TextPaint
import android.text.style.RelativeSizeSpan
import android.text.style.StyleSpan
import android.util.TypedValue
import android.widget.TextView
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material3.Divider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.example.epilogue.domain.model.DigestArticle
import com.example.epilogue.ui.LocalVolumeKeyHandler
import com.example.epilogue.ui.VolumeKeyEvent

/**
 * Represents a page of content in the book reader.
 * Contains the spannable text to display for this page.
 */
private data class BookPage(
    val text: CharSequence,
    val pageNumber: Int
)

/**
 * Represents a chapter (article) with its content and metadata.
 */
private data class Chapter(
    val title: String,
    val author: String,
    val feedName: String,
    val content: SpannableStringBuilder
)

/**
 * E-ink optimized book reader that combines all articles into one continuous
 * paginated text flow, like a real e-book reader.
 *
 * Features:
 * - All articles combined into one continuous text
 * - Article titles become chapter headings
 * - Proper text pagination that flows across pages
 * - Page navigation via tap zones, buttons, and volume keys
 * - Optimized for e-ink displays (no animations, high contrast)
 */
@Composable
fun EinkBookReader(
    articles: List<DigestArticle>,
    modifier: Modifier = Modifier
) {
    val volumeKeyHandler = LocalVolumeKeyHandler.current
    val density = LocalDensity.current

    var currentPage by rememberSaveable { mutableIntStateOf(0) }
    var viewportWidth by remember { mutableStateOf(0) }
    var viewportHeight by remember { mutableStateOf(0) }

    val textColor = MaterialTheme.colorScheme.onSurface.toArgb()

    // Build chapters from articles
    val chapters = remember(articles) {
        articles.map { article -> buildChapter(article) }
    }

    // Calculate pages when viewport dimensions are known
    // Each chapter starts on a new page
    val pages = remember(chapters, viewportWidth, viewportHeight, density) {
        if (viewportWidth <= 0 || viewportHeight <= 0) {
            emptyList()
        } else {
            val textSizePx = with(density) { 17.dp.toPx() }
            paginateChapters(
                chapters = chapters,
                viewportWidth = viewportWidth,
                viewportHeight = viewportHeight,
                textSizePx = textSizePx,
                lineSpacingMultiplier = 1.5f,
                lineSpacingExtra = with(density) { 4.dp.toPx() }
            )
        }
    }

    val totalPages = pages.size.coerceAtLeast(1)

    // Ensure currentPage is within bounds
    LaunchedEffect(totalPages) {
        if (currentPage >= totalPages) {
            currentPage = (totalPages - 1).coerceAtLeast(0)
        }
    }

    // Handle volume key events
    LaunchedEffect(volumeKeyHandler) {
        volumeKeyHandler?.events?.collect { event ->
            when (event) {
                VolumeKeyEvent.VolumeUp -> {
                    if (currentPage > 0) currentPage--
                }
                VolumeKeyEvent.VolumeDown -> {
                    if (currentPage < totalPages - 1) currentPage++
                }
            }
        }
    }

    if (articles.isEmpty()) {
        Box(
            modifier = modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "No articles to display",
                style = MaterialTheme.typography.bodyLarge
            )
        }
        return
    }

    Column(modifier = modifier.fillMaxSize()) {
        // Main content area with tap navigation
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .onGloballyPositioned { coordinates ->
                    viewportWidth = coordinates.size.width
                    viewportHeight = coordinates.size.height
                }
                .pointerInput(totalPages, currentPage) {
                    detectTapGestures { offset ->
                        val width = size.width
                        when {
                            offset.x < width / 3 && currentPage > 0 -> currentPage--
                            offset.x > width * 2 / 3 && currentPage < totalPages - 1 -> currentPage++
                        }
                    }
                }
        ) {
            if (pages.isNotEmpty() && currentPage < pages.size) {
                val pageContent = pages[currentPage]

                // Render the page content
                AndroidView(
                    factory = { ctx ->
                        TextView(ctx).apply {
                            setTextColor(textColor)
                            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
                            setLineSpacing(4f, 1.5f)
                            typeface = Typeface.create("serif", Typeface.NORMAL)
                            includeFontPadding = false
                            setPadding(
                                (20 * ctx.resources.displayMetrics.density).toInt(),
                                (16 * ctx.resources.displayMetrics.density).toInt(),
                                (20 * ctx.resources.displayMetrics.density).toInt(),
                                (16 * ctx.resources.displayMetrics.density).toInt()
                            )
                        }
                    },
                    update = { textView ->
                        textView.text = pageContent.text
                        textView.setTextColor(textColor)
                    },
                    modifier = Modifier.fillMaxSize()
                )
            } else {
                // Loading state while calculating pages
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "Preparing pages...",
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
        }

        // Navigation bar
        BookNavigationBar(
            currentPage = currentPage,
            totalPages = totalPages,
            onPrevious = { if (currentPage > 0) currentPage-- },
            onNext = { if (currentPage < totalPages - 1) currentPage++ },
            modifier = Modifier.fillMaxWidth()
        )
    }
}

/**
 * Builds a chapter from an article with proper styling.
 */
private fun buildChapter(article: DigestArticle): Chapter {
    val builder = SpannableStringBuilder()

    // Chapter title (article title)
    val titleStart = builder.length
    builder.append(article.title)
    val titleEnd = builder.length

    // Style the title: bold and larger
    builder.setSpan(
        StyleSpan(Typeface.BOLD),
        titleStart,
        titleEnd,
        Spanned.SPAN_EXCLUSIVE_EXCLUSIVE
    )
    builder.setSpan(
        RelativeSizeSpan(1.3f),
        titleStart,
        titleEnd,
        Spanned.SPAN_EXCLUSIVE_EXCLUSIVE
    )

    builder.append("\n")

    // Author and source (if available)
    if (article.author.isNotBlank()) {
        val authorStart = builder.length
        builder.append("By ${article.author}")
        val authorEnd = builder.length
        builder.setSpan(
            StyleSpan(Typeface.ITALIC),
            authorStart,
            authorEnd,
            Spanned.SPAN_EXCLUSIVE_EXCLUSIVE
        )
        builder.append(" • ")
    }

    val sourceStart = builder.length
    builder.append(article.feedName)
    val sourceEnd = builder.length
    builder.setSpan(
        RelativeSizeSpan(0.85f),
        sourceStart,
        sourceEnd,
        Spanned.SPAN_EXCLUSIVE_EXCLUSIVE
    )

    builder.append("\n\n")

    // Article content - strip HTML tags and clean up
    val cleanContent = stripHtmlTags(article.content)
    builder.append(cleanContent)

    return Chapter(
        title = article.title,
        author = article.author,
        feedName = article.feedName,
        content = builder
    )
}

/**
 * Strips HTML tags from content and returns plain text.
 * Aggressively removes excessive whitespace.
 */
private fun stripHtmlTags(html: String): String {
    return html
        // Handle block elements - add newlines
        .replace(Regex("<br\\s*/?>", RegexOption.IGNORE_CASE), "\n")
        .replace(Regex("</?p[^>]*>", RegexOption.IGNORE_CASE), "\n")
        .replace(Regex("</?div[^>]*>", RegexOption.IGNORE_CASE), "\n")
        .replace(Regex("</?blockquote[^>]*>", RegexOption.IGNORE_CASE), "\n")
        .replace(Regex("</?h[1-6][^>]*>", RegexOption.IGNORE_CASE), "\n")
        .replace(Regex("</?li[^>]*>", RegexOption.IGNORE_CASE), "\n")
        .replace(Regex("</?ul[^>]*>", RegexOption.IGNORE_CASE), "\n")
        .replace(Regex("</?ol[^>]*>", RegexOption.IGNORE_CASE), "\n")
        // Remove all other HTML tags
        .replace(Regex("<[^>]+>"), "")
        // Decode HTML entities
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&#x27;", "'")
        .replace("&mdash;", "—")
        .replace("&ndash;", "–")
        .replace("&hellip;", "…")
        .replace(Regex("&#(\\d+);")) { matchResult ->
            val code = matchResult.groupValues[1].toIntOrNull()
            if (code != null && code in 32..126) code.toChar().toString() else ""
        }
        // Normalize whitespace: convert tabs and multiple spaces to single space
        .replace("\t", " ")
        .replace(Regex(" {2,}"), " ")
        // Trim whitespace from each line
        .split("\n")
        .joinToString("\n") { it.trim() }
        // Remove excessive blank lines (more than 2 newlines -> 2 newlines)
        .replace(Regex("\n{3,}"), "\n\n")
        // Remove blank lines at the start
        .trimStart('\n', ' ')
        // Remove blank lines at the end
        .trimEnd('\n', ' ')
}

/**
 * Paginates chapters into pages, ensuring each chapter starts on a new page.
 * Uses StaticLayout to accurately measure text.
 */
private fun paginateChapters(
    chapters: List<Chapter>,
    viewportWidth: Int,
    viewportHeight: Int,
    textSizePx: Float,
    lineSpacingMultiplier: Float,
    lineSpacingExtra: Float
): List<BookPage> {
    if (chapters.isEmpty()) return emptyList()

    val pages = mutableListOf<BookPage>()
    var pageNumber = 1

    // Create TextPaint matching the TextView configuration
    val textPaint = TextPaint().apply {
        textSize = textSizePx
        typeface = Typeface.create("serif", Typeface.NORMAL)
        isAntiAlias = true
    }

    // Account for padding (20dp horizontal, 16dp vertical on each side)
    val paddingHorizontal = 40 * (textSizePx / 17f) // Approximate density
    val paddingVertical = 32 * (textSizePx / 17f)
    val availableWidth = (viewportWidth - paddingHorizontal).toInt().coerceAtLeast(100)
    val availableHeight = (viewportHeight - paddingVertical).toInt().coerceAtLeast(100)

    // Process each chapter separately - each chapter starts on a new page
    for (chapter in chapters) {
        val content = chapter.content
        if (content.isEmpty()) continue

        var currentStart = 0

        while (currentStart < content.length) {
            // Create a StaticLayout for the remaining content of this chapter
            val remainingContent = SpannableStringBuilder(content.subSequence(currentStart, content.length))

            val layout = StaticLayout.Builder.obtain(
                remainingContent,
                0,
                remainingContent.length,
                textPaint,
                availableWidth
            )
                .setAlignment(Layout.Alignment.ALIGN_NORMAL)
                .setLineSpacing(lineSpacingExtra, lineSpacingMultiplier)
                .setIncludePad(false)
                .build()

            // Find how many lines fit in the available height
            var linesInPage = 0

            for (line in 0 until layout.lineCount) {
                val lineBottom = layout.getLineBottom(line)
                if (lineBottom > availableHeight) {
                    break
                }
                linesInPage = line + 1
            }

            if (linesInPage == 0) {
                // If not even one line fits, force at least one line
                linesInPage = 1
            }

            // Get the character offset at the end of the last line that fits
            val endOffset = if (linesInPage >= layout.lineCount) {
                remainingContent.length
            } else {
                layout.getLineEnd(linesInPage - 1)
            }

            // Extract the page content
            val pageText = remainingContent.subSequence(0, endOffset)
            pages.add(BookPage(pageText, pageNumber))

            currentStart += endOffset
            pageNumber++

            // Safety check to prevent infinite loops
            if (endOffset == 0) break
        }
    }

    return pages
}

/**
 * Navigation bar for the book reader with page controls.
 */
@Composable
private fun BookNavigationBar(
    currentPage: Int,
    totalPages: Int,
    onPrevious: () -> Unit,
    onNext: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(modifier = modifier.background(MaterialTheme.colorScheme.surface)) {
        Divider(color = MaterialTheme.colorScheme.outline)

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedButton(
                onClick = onPrevious,
                enabled = currentPage > 0,
                modifier = Modifier.height(56.dp)
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.KeyboardArrowLeft,
                    contentDescription = "Previous page",
                    modifier = Modifier.size(24.dp)
                )
                Text("Prev")
            }

            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = "${currentPage + 1} of $totalPages",
                    style = MaterialTheme.typography.titleMedium,
                    textAlign = TextAlign.Center
                )
                Text(
                    text = "Tap sides to turn",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            OutlinedButton(
                onClick = onNext,
                enabled = currentPage < totalPages - 1,
                modifier = Modifier.height(56.dp)
            ) {
                Text("Next")
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.KeyboardArrowRight,
                    contentDescription = "Next page",
                    modifier = Modifier.size(24.dp)
                )
            }
        }
    }
}
