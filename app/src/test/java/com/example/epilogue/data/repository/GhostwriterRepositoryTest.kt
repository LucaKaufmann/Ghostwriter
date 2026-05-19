package com.example.epilogue.data.repository

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class GhostwriterRepositoryTest {

    @get:Rule
    val tempFolder = TemporaryFolder()

    @Test
    fun `resolveDigestOutputFile accepts safe basenames inside documents directory`() {
        val documentsDir = tempFolder.newFolder("Epilogue")

        val outputFile = resolveDigestOutputFile(documentsDir, "digest.epub")

        assertEquals(File(documentsDir, "digest.epub").canonicalFile, outputFile)
    }

    @Test
    fun `resolveDigestOutputFile rejects path traversal and absolute paths`() {
        val documentsDir = tempFolder.newFolder("Epilogue")
        val unsafeNames = listOf(
            "../escape.epub",
            "/tmp/escape.epub",
            "nested/escape.epub",
            "nested\\escape.epub",
            ".",
            "..",
            ""
        )

        unsafeNames.forEach { filename ->
            val thrown = try {
                resolveDigestOutputFile(documentsDir, filename)
                false
            } catch (e: IllegalArgumentException) {
                true
            }
            assertTrue("Expected $filename to be rejected", thrown)
        }
    }
}
