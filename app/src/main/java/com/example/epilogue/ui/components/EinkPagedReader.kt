package com.example.epilogue.ui.components

import android.graphics.Typeface
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import android.text.method.LinkMovementMethod
import android.util.TypedValue
import android.widget.TextView
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.text.HtmlCompat
import com.example.epilogue.domain.model.DigestArticle
import com.example.epilogue.ui.LocalVolumeKeyHandler
import com.example.epilogue.ui.VolumeKeyEvent
import kotlin.math.ceil

/**
 * A page of content to display
 */
private sealed class PageContent {
    data class SectionHeader(val title: String, val subtitle: String) : PageContent()
    data class ArticleStart(val article: DigestArticle) : PageContent()
    data class ArticleContinuation(val article: DigestArticle, val pageInArticle: Int, val totalPagesInArticle: Int) : PageContent()
}

/**
 * E-ink optimized paginated reader that displays digest content like an e-reader.
 * - No scrolling - content is paginated
 * - Page-based navigation only (buttons and volume keys)
 * - Articles always start on a new page
 * - Long articles can span multiple pages
 * - Tap left/right sides of screen to navigate
 */
@Composable
fun EinkPagedReader(
    briefings: List<DigestArticle>,
    deepDives: List<DigestArticle>,
    modifier: Modifier = Modifier
) {
    val volumeKeyHandler = LocalVolumeKeyHandler.current
    val context = LocalContext.current
    val density = LocalDensity.current

    var currentPage by rememberSaveable { mutableIntStateOf(0) }
    var showNavigationBar by rememberSaveable { mutableStateOf(true) }
    var viewportHeight by remember { mutableStateOf(0) }

    // Build flat list of all content items
    val contentItems = remember(briefings, deepDives) {
        buildList {
            if (briefings.isNotEmpty()) {
                add(PageContent.SectionHeader("The Briefing", "AI-generated summaries"))
                briefings.forEach { add(PageContent.ArticleStart(it)) }
            }
            if (deepDives.isNotEmpty()) {
                add(PageContent.SectionHeader("Deep Dives", "Full articles for in-depth reading"))
                deepDives.forEach { add(PageContent.ArticleStart(it)) }
            }
        }
    }

    // Calculate pages when viewport is known
    val pages = remember(contentItems, viewportHeight) {
        if (viewportHeight <= 0) {
            listOf(contentItems.firstOrNull()?.let { listOf(it) } ?: emptyList())
        } else {
            // For now, simple pagination: one item per page
            // Each article gets its own page(s)
            buildList {
                contentItems.forEach { item ->
                    add(listOf(item))
                }
            }
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
    LaunchedEffect(volumeKeyHandler, totalPages) {
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

    if (contentItems.isEmpty()) {
        Box(
            modifier = modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = "No articles in this digest",
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
                    viewportHeight = coordinates.size.height
                }
                .pointerInput(totalPages, currentPage) {
                    detectTapGestures { offset ->
                        val width = size.width
                        when {
                            offset.x < width / 3 && currentPage > 0 -> currentPage--
                            offset.x > width * 2 / 3 && currentPage < totalPages - 1 -> currentPage++
                            else -> showNavigationBar = !showNavigationBar
                        }
                    }
                }
                .pointerInput(totalPages, currentPage) {
                    var totalDrag = 0f
                    detectHorizontalDragGestures(
                        onDragStart = { totalDrag = 0f },
                        onDragEnd = {
                            val swipeThreshold = size.width * 0.15f
                            when {
                                totalDrag > swipeThreshold && currentPage > 0 -> currentPage--
                                totalDrag < -swipeThreshold && currentPage < totalPages - 1 -> currentPage++
                            }
                        },
                        onHorizontalDrag = { _, dragAmount ->
                            totalDrag += dragAmount
                        }
                    )
                }
        ) {
            // Render current page content
            val currentPageContent = pages.getOrNull(currentPage) ?: emptyList()

            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 8.dp)
            ) {
                currentPageContent.forEach { item ->
                    when (item) {
                        is PageContent.SectionHeader -> {
                            SectionHeaderContent(item.title, item.subtitle)
                        }
                        is PageContent.ArticleStart -> {
                            ArticlePageContent(article = item.article)
                        }
                        is PageContent.ArticleContinuation -> {
                            ArticleContinuationContent(
                                article = item.article,
                                pageNum = item.pageInArticle,
                                totalPages = item.totalPagesInArticle
                            )
                        }
                    }
                }
            }
        }

        // Navigation bar (toggle with center tap)
        if (showNavigationBar) {
            PageNavigationBar(
                currentPage = currentPage,
                totalPages = totalPages,
                onPrevious = { if (currentPage > 0) currentPage-- },
                onNext = { if (currentPage < totalPages - 1) currentPage++ },
                modifier = Modifier.fillMaxWidth()
            )
        }
    }
}

@Composable
private fun SectionHeaderContent(title: String, subtitle: String) {
    Column {
        Text(
            text = title,
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = subtitle,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.height(8.dp))
        Divider()
    }
}

@Composable
private fun ArticlePageContent(
    article: DigestArticle,
    modifier: Modifier = Modifier
) {
    val textColor = MaterialTheme.colorScheme.onSurface.toArgb()
    val linkColor = MaterialTheme.colorScheme.primary.toArgb()

    Column(modifier = modifier.fillMaxWidth()) {
        // Article header
        Text(
            text = article.title,
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold
        )

        if (article.author.isNotBlank()) {
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "By ${article.author}",
                style = MaterialTheme.typography.bodyMedium,
                fontStyle = FontStyle.Italic,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }

        Text(
            text = article.feedName,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Spacer(modifier = Modifier.height(12.dp))

        // Article content
        val htmlContent = remember(article.content) {
            HtmlCompat.fromHtml(article.content, HtmlCompat.FROM_HTML_MODE_LEGACY)
        }

        AndroidView(
            factory = { context ->
                TextView(context).apply {
                    setTextColor(textColor)
                    setLinkTextColor(linkColor)
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
                    setLineSpacing(4f, 1.4f)
                    typeface = Typeface.create("serif", Typeface.NORMAL)
                    movementMethod = LinkMovementMethod.getInstance()
                    includeFontPadding = false
                    // Limit lines to prevent overflow - content will be truncated
                    maxLines = 25
                }
            },
            update = { textView ->
                textView.text = htmlContent
                textView.setTextColor(textColor)
                textView.setLinkTextColor(linkColor)
            },
            modifier = Modifier.fillMaxWidth()
        )
    }
}

@Composable
private fun ArticleContinuationContent(
    article: DigestArticle,
    pageNum: Int,
    totalPages: Int,
    modifier: Modifier = Modifier
) {
    val textColor = MaterialTheme.colorScheme.onSurface.toArgb()
    val linkColor = MaterialTheme.colorScheme.primary.toArgb()

    Column(modifier = modifier.fillMaxWidth()) {
        // Continuation header
        Text(
            text = "${article.title} (continued)",
            style = MaterialTheme.typography.titleMedium,
            fontStyle = FontStyle.Italic,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = "Page $pageNum of $totalPages",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Spacer(modifier = Modifier.height(12.dp))

        // This is a simplified version - in a real implementation,
        // we'd need to calculate which portion of text to show
        val htmlContent = remember(article.content) {
            HtmlCompat.fromHtml(article.content, HtmlCompat.FROM_HTML_MODE_LEGACY)
        }

        AndroidView(
            factory = { context ->
                TextView(context).apply {
                    setTextColor(textColor)
                    setLinkTextColor(linkColor)
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
                    setLineSpacing(4f, 1.4f)
                    typeface = Typeface.create("serif", Typeface.NORMAL)
                    movementMethod = LinkMovementMethod.getInstance()
                    includeFontPadding = false
                }
            },
            update = { textView ->
                textView.text = htmlContent
                textView.setTextColor(textColor)
                textView.setLinkTextColor(linkColor)
            },
            modifier = Modifier.fillMaxWidth()
        )
    }
}

/**
 * Navigation bar for page-based navigation.
 */
@Composable
private fun PageNavigationBar(
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
                .padding(horizontal = 12.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedButton(
                onClick = onPrevious,
                enabled = currentPage > 0,
                modifier = Modifier.height(40.dp)
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.KeyboardArrowLeft,
                    contentDescription = "Previous page",
                    modifier = Modifier.size(20.dp)
                )
                Text("Prev")
            }

            Text(
                text = "${currentPage + 1} / $totalPages",
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center
            )

            OutlinedButton(
                onClick = onNext,
                enabled = currentPage < totalPages - 1,
                modifier = Modifier.height(40.dp)
            ) {
                Text("Next")
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.KeyboardArrowRight,
                    contentDescription = "Next page",
                    modifier = Modifier.size(20.dp)
                )
            }
        }
    }
}
