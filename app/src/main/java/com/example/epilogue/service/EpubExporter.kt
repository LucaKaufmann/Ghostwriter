package com.example.epilogue.service

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.util.Log
import com.example.epilogue.data.repository.SettingsRepository
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Result of exporting an EPUB to a custom directory.
 */
sealed class ExportResult {
    data object Success : ExportResult()
    data object NotConfigured : ExportResult()
    data object PermissionRevoked : ExportResult()
    data class Error(val message: String) : ExportResult()
}

/**
 * Service for exporting EPUB files to user-selected directories via SAF.
 */
@Singleton
class EpubExporter @Inject constructor(
    @ApplicationContext private val context: Context,
    private val settingsRepository: SettingsRepository
) {

    companion object {
        private const val TAG = "EpubExporter"
        private const val MIME_TYPE_EPUB = "application/epub+zip"
    }

    /**
     * Copies the EPUB file to the custom export directory if configured.
     * Returns the result of the operation.
     */
    suspend fun exportToCustomDirectory(sourceFile: File): ExportResult =
        withContext(Dispatchers.IO) {
            if (!settingsRepository.isCustomExportEnabled()) {
                return@withContext ExportResult.NotConfigured
            }

            val uriString = settingsRepository.getCustomExportUri()
                ?: return@withContext ExportResult.NotConfigured

            val treeUri = try {
                Uri.parse(uriString)
            } catch (e: Exception) {
                Log.e(TAG, "Invalid URI: $uriString", e)
                return@withContext ExportResult.Error("Invalid export directory URI")
            }

            if (!hasPermission(treeUri)) {
                Log.w(TAG, "Permission revoked for: $uriString")
                return@withContext ExportResult.PermissionRevoked
            }

            try {
                copyFileToSafDirectory(sourceFile, treeUri)
                Log.i(TAG, "Exported ${sourceFile.name} to custom directory")
                ExportResult.Success
            } catch (e: Exception) {
                Log.e(TAG, "Export failed", e)
                ExportResult.Error(e.message ?: "Unknown error during export")
            }
        }

    /**
     * Checks if we still have write permission to the given tree URI.
     */
    private fun hasPermission(treeUri: Uri): Boolean {
        val persistedUris = context.contentResolver.persistedUriPermissions
        return persistedUris.any {
            it.uri == treeUri && it.isWritePermission
        }
    }

    /**
     * Copies a file to the SAF directory using DocumentsContract.
     */
    private fun copyFileToSafDirectory(sourceFile: File, treeUri: Uri) {
        val resolver = context.contentResolver

        val docUri = DocumentsContract.buildDocumentUriUsingTree(
            treeUri,
            DocumentsContract.getTreeDocumentId(treeUri)
        )

        // Check if file already exists and delete it
        deleteExistingFile(docUri, sourceFile.name)

        // Create new file in the SAF directory
        val newDocUri = DocumentsContract.createDocument(
            resolver,
            docUri,
            MIME_TYPE_EPUB,
            sourceFile.nameWithoutExtension
        ) ?: throw IOException("Failed to create document in export directory")

        // Copy content
        resolver.openOutputStream(newDocUri)?.use { output ->
            sourceFile.inputStream().use { input ->
                input.copyTo(output)
            }
        } ?: throw IOException("Failed to open output stream for export")
    }

    /**
     * Deletes an existing file with the same name if it exists.
     */
    private fun deleteExistingFile(parentDocUri: Uri, fileName: String) {
        try {
            val resolver = context.contentResolver
            val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(
                parentDocUri,
                DocumentsContract.getDocumentId(parentDocUri)
            )

            resolver.query(
                childrenUri,
                arrayOf(
                    DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                    DocumentsContract.Document.COLUMN_DISPLAY_NAME
                ),
                null,
                null,
                null
            )?.use { cursor ->
                while (cursor.moveToNext()) {
                    val displayName = cursor.getString(1)
                    if (displayName == fileName) {
                        val docId = cursor.getString(0)
                        val docToDelete = DocumentsContract.buildDocumentUriUsingTree(
                            parentDocUri,
                            docId
                        )
                        DocumentsContract.deleteDocument(resolver, docToDelete)
                        Log.d(TAG, "Deleted existing file: $fileName")
                        break
                    }
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Could not check/delete existing file: ${e.message}")
        }
    }

    /**
     * Validates stored URI permissions are still valid.
     * Should be called on app startup.
     * @return true if permission is valid or not configured, false if permission was revoked
     */
    fun validateStoredPermissions(): Boolean {
        val uriString = settingsRepository.getCustomExportUri() ?: return true
        val treeUri = try {
            Uri.parse(uriString)
        } catch (e: Exception) {
            return false
        }

        return hasPermission(treeUri)
    }
}
