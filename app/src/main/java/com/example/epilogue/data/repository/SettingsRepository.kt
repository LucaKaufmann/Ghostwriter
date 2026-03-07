package com.example.epilogue.data.repository

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.example.epilogue.domain.model.DigestPeriod
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
        private const val KEY_SCHEDULE_HOUR = "schedule_hour"  // Legacy, for migration
        private const val KEY_SCHEDULE_MINUTE = "schedule_minute"  // Legacy, for migration
        private const val KEY_SCHEDULE_PERIODS = "schedule_periods"
        private const val KEY_SCHEDULE_MIGRATED = "schedule_migrated"
        private const val KEY_SCHEDULE_LAST_CATCH_UP_DATE_PREFIX = "schedule_last_catch_up_date_"
        private const val KEY_MIN_WORD_COUNT = "min_word_count"
        private const val KEY_EINK_MODE = "eink_mode"
        private const val KEY_CUSTOM_EXPORT_URI = "custom_export_uri"
        private const val KEY_CUSTOM_EXPORT_ENABLED = "custom_export_enabled"

        // Ghostwriter settings keys
        private const val KEY_GHOSTWRITER_ENABLED = "ghostwriter_enabled"
        private const val KEY_GHOSTWRITER_URL = "ghostwriter_url"
        private const val KEY_GHOSTWRITER_DOWNLOAD_EPUBS_ON_SYNC = "ghostwriter_download_epubs_on_sync"
        private const val KEY_GHOSTWRITER_USE_SHARED_CLIENT = "ghostwriter_use_shared_client"

        // Encrypted settings keys
        private const val KEY_OPENAI_API_KEY = "openai_api_key"
        private const val KEY_GHOSTWRITER_API_KEY = "ghostwriter_api_key"

        // Sync tracking
        private const val KEY_LAST_DIGEST_SYNC = "last_digest_sync"
        private const val KEY_LAST_FEED_SYNC = "last_feed_sync"
        private const val KEY_CONFIG_UPDATED_AT = "config_updated_at"  // Server's updated_at timestamp

        // Ghostwriter schedule display keys
        private const val KEY_GW_MORNING_HOUR = "gw_morning_hour"
        private const val KEY_GW_MORNING_MINUTE = "gw_morning_minute"
        private const val KEY_GW_NOON_HOUR = "gw_noon_hour"
        private const val KEY_GW_NOON_MINUTE = "gw_noon_minute"
        private const val KEY_GW_EVENING_HOUR = "gw_evening_hour"
        private const val KEY_GW_EVENING_MINUTE = "gw_evening_minute"
        private const val KEY_GW_TIMEZONE = "gw_timezone"

        // Defaults
        private const val DEFAULT_MIN_WORD_COUNT = 0
        private const val DEFAULT_EINK_MODE = false
        private const val DEFAULT_CUSTOM_EXPORT_ENABLED = false
        private const val DEFAULT_GHOSTWRITER_ENABLED = false
        private const val DEFAULT_GHOSTWRITER_DOWNLOAD_EPUBS_ON_SYNC = true
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

    // E-ink mode state flow for reactive updates
    private val _einkModeFlow = MutableStateFlow(false)
    val einkModeFlow: Flow<Boolean> = _einkModeFlow.asStateFlow()

    // Custom export state flows for reactive updates
    private val _customExportUriFlow = MutableStateFlow<String?>(null)
    val customExportUriFlow: Flow<String?> = _customExportUriFlow.asStateFlow()

    private val _customExportEnabledFlow = MutableStateFlow(false)
    val customExportEnabledFlow: Flow<Boolean> = _customExportEnabledFlow.asStateFlow()

    // Ghostwriter state flows
    private val _ghostwriterEnabledFlow = MutableStateFlow(false)
    val ghostwriterEnabledFlow: Flow<Boolean> = _ghostwriterEnabledFlow.asStateFlow()

    private val _ghostwriterUrlFlow = MutableStateFlow<String?>(null)
    val ghostwriterUrlFlow: Flow<String?> = _ghostwriterUrlFlow.asStateFlow()

    private val _ghostwriterApiKeyFlow = MutableStateFlow<String?>(null)
    val ghostwriterApiKeyFlow: Flow<String?> = _ghostwriterApiKeyFlow.asStateFlow()

    init {
        // Initialize API key flow
        _apiKeyFlow.value = getOpenAIApiKey()
        // Initialize e-ink mode flow
        _einkModeFlow.value = getEinkMode()
        // Initialize custom export flows
        _customExportUriFlow.value = getCustomExportUri()
        _customExportEnabledFlow.value = isCustomExportEnabled()
        // Initialize Ghostwriter flows
        _ghostwriterEnabledFlow.value = isGhostwriterEnabled()
        _ghostwriterUrlFlow.value = getGhostwriterUrl()
        _ghostwriterApiKeyFlow.value = getGhostwriterApiKey()
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
     * Gets the selected digest periods.
     * Performs migration from legacy hour/minute settings if needed.
     */
    fun getSchedulePeriods(): Set<DigestPeriod> {
        // Check if migration is needed
        if (!prefs.getBoolean(KEY_SCHEDULE_MIGRATED, false)) {
            migrateScheduleSettings()
        }

        val periodsString = prefs.getString(KEY_SCHEDULE_PERIODS, null)
        if (periodsString.isNullOrEmpty()) {
            // Default to Evening if nothing selected
            return setOf(DigestPeriod.EVENING)
        }

        return periodsString.split(",")
            .mapNotNull { name ->
                try {
                    DigestPeriod.valueOf(name)
                } catch (e: IllegalArgumentException) {
                    null
                }
            }
            .toSet()
    }

    /**
     * Sets the selected digest periods.
     */
    suspend fun setSchedulePeriods(periods: Set<DigestPeriod>) = withContext(Dispatchers.IO) {
        val periodsString = periods.joinToString(",") { it.name }
        prefs.edit()
            .putString(KEY_SCHEDULE_PERIODS, periodsString)
            .apply()
    }

    /**
     * Toggles a specific period on or off.
     */
    suspend fun toggleSchedulePeriod(period: DigestPeriod, enabled: Boolean) = withContext(Dispatchers.IO) {
        val currentPeriods = getSchedulePeriods().toMutableSet()
        if (enabled) {
            currentPeriods.add(period)
        } else {
            currentPeriods.remove(period)
            prefs.edit()
                .remove("${KEY_SCHEDULE_LAST_CATCH_UP_DATE_PREFIX}${period.name}")
                .apply()
        }
        setSchedulePeriods(currentPeriods)
    }

    /**
     * Stores the last date (YYYY-MM-DD) when a catch-up run was enqueued for a period.
     */
    suspend fun setLastCatchUpDate(period: DigestPeriod, date: String) = withContext(Dispatchers.IO) {
        prefs.edit()
            .putString("${KEY_SCHEDULE_LAST_CATCH_UP_DATE_PREFIX}${period.name}", date)
            .apply()
    }

    /**
     * Returns the last date (YYYY-MM-DD) when a catch-up run was enqueued for a period.
     */
    fun getLastCatchUpDate(period: DigestPeriod): String? {
        return prefs.getString("${KEY_SCHEDULE_LAST_CATCH_UP_DATE_PREFIX}${period.name}", null)
    }

    /**
     * Migrates legacy hour/minute schedule to period-based schedule.
     */
    private fun migrateScheduleSettings() {
        val legacyHour = prefs.getInt(KEY_SCHEDULE_HOUR, -1)
        if (legacyHour != -1) {
            // User had a schedule set, migrate to nearest period
            val period = DigestPeriod.fromHour(legacyHour)
            prefs.edit()
                .putString(KEY_SCHEDULE_PERIODS, period.name)
                .putBoolean(KEY_SCHEDULE_MIGRATED, true)
                .apply()
        } else {
            // No legacy schedule, just mark as migrated
            prefs.edit()
                .putBoolean(KEY_SCHEDULE_MIGRATED, true)
                .apply()
        }
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

    // ===== E-ink Mode Settings =====

    /**
     * Sets the e-ink mode enabled state.
     * When enabled, optimizes UI for e-ink displays.
     */
    suspend fun setEinkMode(enabled: Boolean) = withContext(Dispatchers.IO) {
        prefs.edit()
            .putBoolean(KEY_EINK_MODE, enabled)
            .apply()
        _einkModeFlow.value = enabled
    }

    /**
     * Gets whether e-ink mode is enabled.
     */
    fun getEinkMode(): Boolean {
        return prefs.getBoolean(KEY_EINK_MODE, DEFAULT_EINK_MODE)
    }

    // ===== Custom Export Settings =====

    /**
     * Sets the custom export directory URI (from SAF).
     */
    suspend fun setCustomExportUri(uriString: String?) = withContext(Dispatchers.IO) {
        if (uriString.isNullOrBlank()) {
            prefs.edit().remove(KEY_CUSTOM_EXPORT_URI).apply()
        } else {
            prefs.edit().putString(KEY_CUSTOM_EXPORT_URI, uriString).apply()
        }
        _customExportUriFlow.value = uriString
    }

    /**
     * Gets the custom export directory URI string.
     */
    fun getCustomExportUri(): String? {
        return prefs.getString(KEY_CUSTOM_EXPORT_URI, null)
    }

    /**
     * Sets whether custom export is enabled.
     */
    suspend fun setCustomExportEnabled(enabled: Boolean) = withContext(Dispatchers.IO) {
        prefs.edit()
            .putBoolean(KEY_CUSTOM_EXPORT_ENABLED, enabled)
            .apply()
        _customExportEnabledFlow.value = enabled
    }

    /**
     * Gets whether custom export is enabled.
     */
    fun isCustomExportEnabled(): Boolean {
        return prefs.getBoolean(KEY_CUSTOM_EXPORT_ENABLED, DEFAULT_CUSTOM_EXPORT_ENABLED)
    }

    // ===== Ghostwriter Settings =====

    /**
     * Sets whether Ghostwriter backend is enabled.
     */
    suspend fun setGhostwriterEnabled(enabled: Boolean) = withContext(Dispatchers.IO) {
        prefs.edit()
            .putBoolean(KEY_GHOSTWRITER_ENABLED, enabled)
            .apply()
        _ghostwriterEnabledFlow.value = enabled
    }

    /**
     * Gets whether Ghostwriter backend is enabled.
     */
    fun isGhostwriterEnabled(): Boolean {
        return prefs.getBoolean(KEY_GHOSTWRITER_ENABLED, DEFAULT_GHOSTWRITER_ENABLED)
    }

    /**
     * Sets the Ghostwriter server URL.
     */
    suspend fun setGhostwriterUrl(url: String?) = withContext(Dispatchers.IO) {
        if (url.isNullOrBlank()) {
            prefs.edit().remove(KEY_GHOSTWRITER_URL).apply()
        } else {
            prefs.edit().putString(KEY_GHOSTWRITER_URL, url.trim()).apply()
        }
        _ghostwriterUrlFlow.value = url?.trim()
    }

    /**
     * Gets the Ghostwriter server URL.
     */
    fun getGhostwriterUrl(): String? {
        return prefs.getString(KEY_GHOSTWRITER_URL, null)
    }

    /**
     * Sets whether synced Ghostwriter digests should automatically download EPUB files.
     */
    suspend fun setGhostwriterDownloadEpubsOnSync(enabled: Boolean) = withContext(Dispatchers.IO) {
        prefs.edit()
            .putBoolean(KEY_GHOSTWRITER_DOWNLOAD_EPUBS_ON_SYNC, enabled)
            .apply()
    }

    /**
     * Gets whether synced Ghostwriter digests should automatically download EPUB files.
     * Defaults to true to preserve existing behavior.
     */
    fun shouldDownloadGhostwriterEpubsOnSync(): Boolean {
        return prefs.getBoolean(
            KEY_GHOSTWRITER_DOWNLOAD_EPUBS_ON_SYNC,
            DEFAULT_GHOSTWRITER_DOWNLOAD_EPUBS_ON_SYNC
        )
    }

    /**
     * Enables KMP-backed shared Ghostwriter client for Android networking path.
     * Defaults to enabled.
     */
    suspend fun setUseSharedGhostwriterClient(enabled: Boolean) = withContext(Dispatchers.IO) {
        prefs.edit()
            .putBoolean(KEY_GHOSTWRITER_USE_SHARED_CLIENT, enabled)
            .apply()
    }

    /**
     * Returns whether the app should use the KMP shared Ghostwriter client path.
     */
    fun useSharedGhostwriterClient(): Boolean {
        return prefs.getBoolean(
            KEY_GHOSTWRITER_USE_SHARED_CLIENT,
            true
        )
    }

    /**
     * Saves the Ghostwriter API key securely.
     */
    suspend fun setGhostwriterApiKey(apiKey: String?) = withContext(Dispatchers.IO) {
        if (apiKey.isNullOrBlank()) {
            encryptedPrefs.edit().remove(KEY_GHOSTWRITER_API_KEY).apply()
        } else {
            encryptedPrefs.edit().putString(KEY_GHOSTWRITER_API_KEY, apiKey.trim()).apply()
        }
        _ghostwriterApiKeyFlow.value = apiKey?.trim()
    }

    /**
     * Retrieves the Ghostwriter API key.
     */
    fun getGhostwriterApiKey(): String? {
        return encryptedPrefs.getString(KEY_GHOSTWRITER_API_KEY, null)
    }

    /**
     * Checks if Ghostwriter is fully configured and enabled.
     */
    fun isGhostwriterConfigured(): Boolean {
        return isGhostwriterEnabled() && !getGhostwriterUrl().isNullOrBlank()
    }

    // ===== Sync Tracking =====

    /**
     * Sets the last digest sync timestamp.
     */
    suspend fun setLastDigestSyncTime(timestamp: Long) = withContext(Dispatchers.IO) {
        prefs.edit()
            .putLong(KEY_LAST_DIGEST_SYNC, timestamp)
            .apply()
    }

    /**
     * Gets the last digest sync timestamp.
     * Returns 0 if never synced.
     */
    fun getLastDigestSyncTime(): Long {
        return prefs.getLong(KEY_LAST_DIGEST_SYNC, 0L)
    }

    // ===== Feed Sync Tracking =====

    /**
     * Sets the last feed sync timestamp.
     * This is the server_timestamp from the last successful feed sync.
     */
    suspend fun setLastFeedSyncTime(timestamp: Long) = withContext(Dispatchers.IO) {
        prefs.edit()
            .putLong(KEY_LAST_FEED_SYNC, timestamp)
            .apply()
    }

    /**
     * Gets the last feed sync timestamp.
     * Returns 0 if never synced (triggers initial full sync).
     */
    fun getLastFeedSyncTime(): Long {
        return prefs.getLong(KEY_LAST_FEED_SYNC, 0L)
    }

    // ===== Config Sync Tracking =====

    /**
     * Sets the server's config updated_at timestamp.
     * Used for conflict detection during config sync.
     */
    suspend fun setConfigUpdatedAt(timestamp: String?) = withContext(Dispatchers.IO) {
        if (timestamp.isNullOrBlank()) {
            prefs.edit().remove(KEY_CONFIG_UPDATED_AT).apply()
        } else {
            prefs.edit().putString(KEY_CONFIG_UPDATED_AT, timestamp).apply()
        }
    }

    /**
     * Gets the server's config updated_at timestamp.
     * Returns null if never synced.
     */
    fun getConfigUpdatedAt(): String? {
        return prefs.getString(KEY_CONFIG_UPDATED_AT, null)
    }

    // ===== Ghostwriter Schedule (for display) =====

    data class GhostwriterSchedule(
        val morningHour: Int,
        val morningMinute: Int,
        val noonHour: Int,
        val noonMinute: Int,
        val eveningHour: Int,
        val eveningMinute: Int,
        val timezone: String
    )

    fun setGhostwriterSchedule(
        morningHour: Int,
        morningMinute: Int,
        noonHour: Int,
        noonMinute: Int,
        eveningHour: Int,
        eveningMinute: Int,
        timezone: String
    ) {
        prefs.edit()
            .putInt(KEY_GW_MORNING_HOUR, morningHour)
            .putInt(KEY_GW_MORNING_MINUTE, morningMinute)
            .putInt(KEY_GW_NOON_HOUR, noonHour)
            .putInt(KEY_GW_NOON_MINUTE, noonMinute)
            .putInt(KEY_GW_EVENING_HOUR, eveningHour)
            .putInt(KEY_GW_EVENING_MINUTE, eveningMinute)
            .putString(KEY_GW_TIMEZONE, timezone)
            .apply()
    }

    fun getGhostwriterSchedule(): GhostwriterSchedule? {
        val timezone = prefs.getString(KEY_GW_TIMEZONE, null) ?: return null
        return GhostwriterSchedule(
            morningHour = prefs.getInt(KEY_GW_MORNING_HOUR, 7),
            morningMinute = prefs.getInt(KEY_GW_MORNING_MINUTE, 0),
            noonHour = prefs.getInt(KEY_GW_NOON_HOUR, 12),
            noonMinute = prefs.getInt(KEY_GW_NOON_MINUTE, 0),
            eveningHour = prefs.getInt(KEY_GW_EVENING_HOUR, 18),
            eveningMinute = prefs.getInt(KEY_GW_EVENING_MINUTE, 0),
            timezone = timezone
        )
    }
}
