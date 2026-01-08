package com.example.epilogue.data.repository

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository for app settings including secure storage of API keys.
 * Uses EncryptedSharedPreferences for sensitive data.
 */
@Singleton
class SettingsRepository @Inject constructor(
    @ApplicationContext private val context: Context
) {

    companion object {
        private const val PREFS_NAME = "epilog_settings"
        private const val ENCRYPTED_PREFS_NAME = "epilog_secure_settings"

        // Regular settings keys
        private const val KEY_SCHEDULE_HOUR = "schedule_hour"
        private const val KEY_SCHEDULE_MINUTE = "schedule_minute"
        private const val KEY_MIN_WORD_COUNT = "min_word_count"

        // Encrypted settings keys
        private const val KEY_OPENAI_API_KEY = "openai_api_key"

        // Defaults
        private const val DEFAULT_SCHEDULE_HOUR = 22  // 10:00 PM
        private const val DEFAULT_SCHEDULE_MINUTE = 0
        private const val DEFAULT_MIN_WORD_COUNT = 0
    }

    private val prefs: SharedPreferences by lazy {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }

    private val encryptedPrefs: SharedPreferences by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        EncryptedSharedPreferences.create(
            context,
            ENCRYPTED_PREFS_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    // API Key state flow for reactive updates
    private val _apiKeyFlow = MutableStateFlow<String?>(null)
    val apiKeyFlow: Flow<String?> = _apiKeyFlow.asStateFlow()

    init {
        // Initialize API key flow
        _apiKeyFlow.value = getOpenAIApiKey()
    }

    // ===== OpenAI API Key (Encrypted) =====

    /**
     * Saves the OpenAI API key securely.
     */
    suspend fun setOpenAIApiKey(apiKey: String?) = withContext(Dispatchers.IO) {
        if (apiKey.isNullOrBlank()) {
            encryptedPrefs.edit().remove(KEY_OPENAI_API_KEY).apply()
        } else {
            encryptedPrefs.edit().putString(KEY_OPENAI_API_KEY, apiKey.trim()).apply()
        }
        _apiKeyFlow.value = apiKey?.trim()
    }

    /**
     * Retrieves the OpenAI API key.
     */
    fun getOpenAIApiKey(): String? {
        return encryptedPrefs.getString(KEY_OPENAI_API_KEY, null)
    }

    /**
     * Checks if an OpenAI API key is configured.
     */
    fun hasOpenAIApiKey(): Boolean {
        return !getOpenAIApiKey().isNullOrBlank()
    }

    // ===== Schedule Settings =====

    /**
     * Sets the daily digest schedule time.
     */
    suspend fun setScheduleTime(hour: Int, minute: Int) = withContext(Dispatchers.IO) {
        prefs.edit()
            .putInt(KEY_SCHEDULE_HOUR, hour.coerceIn(0, 23))
            .putInt(KEY_SCHEDULE_MINUTE, minute.coerceIn(0, 59))
            .apply()
    }

    /**
     * Gets the scheduled hour (0-23).
     */
    fun getScheduleHour(): Int {
        return prefs.getInt(KEY_SCHEDULE_HOUR, DEFAULT_SCHEDULE_HOUR)
    }

    /**
     * Gets the scheduled minute (0-59).
     */
    fun getScheduleMinute(): Int {
        return prefs.getInt(KEY_SCHEDULE_MINUTE, DEFAULT_SCHEDULE_MINUTE)
    }

    // ===== Content Settings =====

    /**
     * Sets the minimum word count filter for articles.
     */
    suspend fun setMinWordCount(count: Int) = withContext(Dispatchers.IO) {
        prefs.edit()
            .putInt(KEY_MIN_WORD_COUNT, count.coerceAtLeast(0))
            .apply()
    }

    /**
     * Gets the minimum word count filter.
     */
    fun getMinWordCount(): Int {
        return prefs.getInt(KEY_MIN_WORD_COUNT, DEFAULT_MIN_WORD_COUNT)
    }
}
