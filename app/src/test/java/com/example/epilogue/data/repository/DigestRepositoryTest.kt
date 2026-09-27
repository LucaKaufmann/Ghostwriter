package com.example.epilogue.data.repository

import androidx.room.Room
import com.example.epilogue.data.local.DigestEntity
import com.example.epilogue.data.local.EpilogueDatabase
import com.example.epilogue.domain.model.TriggerType
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.Assert.*
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class DigestRepositoryTest {
    @get:Rule val files = TemporaryFolder()
    private lateinit var database: EpilogueDatabase
    private lateinit var repository: DigestRepository

    @Before fun setUp() {
        database = Room.inMemoryDatabaseBuilder(RuntimeEnvironment.getApplication(), EpilogueDatabase::class.java)
            .allowMainThreadQueries().build()
        repository = DigestRepository(database.digestDao())
    }

    @After fun tearDown() { database.close() }

    private suspend fun record(file: File, generatedAt: Long = 1, remoteId: String? = null): DigestEntity {
        val entity = DigestEntity(
            generatedAt = generatedAt, epubFilePath = file.absolutePath, articleCount = 1,
            briefingCount = 0, fidelityCount = 1, triggerType = TriggerType.MANUAL,
            feedNames = "Fixture", remoteId = remoteId
        )
        return entity.copy(id = database.digestDao().insertDigest(entity))
    }

    @Test fun `legacy shared path remains until final reference is deleted`() = runBlocking {
        val file = files.newFile("shared.epub").apply { writeText("shared book") }
        val first = record(file)
        val second = record(file)
        assertTrue(repository.deleteDigest(first.toDomain()))
        assertNull(repository.getDigestById(first.id))
        assertEquals("shared book", file.readText())
        assertNotNull(repository.getDigestById(second.id))
        assertTrue(repository.deleteDigest(second.toDomain()))
        assertFalse(file.exists())
    }

    @Test fun `deletion uses current persisted path instead of stale UI path`() = runBlocking {
        val personal = files.newFile("old.epub").apply { writeText("keep") }
        val current = files.newFile("current.epub")
        val digest = record(personal)
        database.digestDao().updateEpubFilePath(digest.id, current.absolutePath)
        assertTrue(repository.deleteDigest(digest.toDomain()))
        assertEquals("keep", personal.readText())
        assertFalse(current.exists())
    }

    @Test fun `failed unlink retains row for retry and missing file is idempotent`() = runBlocking {
        val directory = files.newFolder("cannot-delete-as-file").apply { resolve("child").writeText("keep") }
        val failed = record(directory)
        assertFalse(repository.deleteDigest(failed.toDomain()))
        assertNotNull(repository.getDigestById(failed.id))
        assertTrue(directory.resolve("child").exists())
        assertFalse(repository.deleteAllDigests())
        assertNotNull(repository.getDigestById(failed.id))
        val missing = record(File(files.root, "missing.epub"))
        assertTrue(repository.deleteDigest(missing.toDomain()))
        assertTrue(repository.deleteDigest(missing.toDomain()))
    }

    @Test fun `retention and remote cache eviction do not remove another live reference`() = runBlocking {
        val shared = files.newFile("shared.epub").apply { writeText("retained") }
        val oldest = record(shared, 0, "old-remote")
        repeat(28) { record(files.newFile("other-$it.epub"), 100L + it) }
        val retained = record(shared, 900)
        shared.setLastModified(1)
        assertEquals(0, repository.cleanupStaleRemoteEpubFiles(1))
        assertTrue(shared.exists())
        repository.saveRemoteDigest("new-remote", files.newFile("new.epub").absolutePath, 1, 1000, "manual")
        assertNull(repository.getDigestById(oldest.id))
        assertNotNull(repository.getDigestById(retained.id))
        assertEquals("retained", shared.readText())
        assertTrue(repository.deleteAllDigests())
        assertFalse(shared.exists())
        assertEquals(0, database.digestDao().getDigestCount())
    }
}
