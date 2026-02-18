// API Types based on the FastAPI backend

// ============ Authentication ============

export interface AuthStatus {
	setup_complete: boolean;
	registration_open: boolean;
}

export interface UserResponse {
	id: string;
	username: string;
	email: string | null;
	is_admin: boolean;
	created_at: string;
	last_login_at: string | null;
}

export interface LoginRequest {
	username: string;
	password: string;
}

export interface RegisterRequest {
	username: string;
	password: string;
	email?: string;
}

export interface LoginResponse {
	access_token: string;
	token_type: string;
	user: UserResponse;
}

export interface UserUpdate {
	email?: string;
	password?: string;
}

export interface APITokenResponse {
	id: string;
	name: string;
	token_prefix: string;
	created_at: string;
	last_used_at: string | null;
	revoked_at: string | null;
}

export interface APITokenCreateRequest {
	name: string;
}

export interface APITokenCreateResponse {
	id: string;
	name: string;
	token: string;
	token_prefix: string;
	created_at: string;
}

export interface KoreaderPluginDownloadRequest {
	token_name: string;
	server_url?: string;
}

// ============ Health & Config ============

export interface HealthResponse {
	status: string;
	version: string;
	uptime_seconds: number | null;
	last_successful_digest: string | null;
	ai_provider: string;
	ai_model: string;
	ai_status?: string | null;
}

export interface IntegrationStatus {
	enabled: boolean;
	label?: string | null;
}

export interface ConfigResponse {
	timezone: string;
	ai_provider: string;
	ai_model: string;
	schedule_enabled: boolean;
	schedule_morning: string;
	schedule_noon: string;
	schedule_evening: string;
	digest_retention_days: number;
	max_articles_per_digest: number;
	wallabag?: IntegrationStatus | null;
	newsletters?: IntegrationStatus | null;
}

export interface ClientConfigResponse {
	min_word_count: number;
	morning_hour: number;
	morning_minute: number;
	noon_hour: number;
	noon_minute: number;
	evening_hour: number;
	evening_minute: number;
	timezone: string;
	whisper_provider: string;
	whisper_model: string;
	whisper_timeout_minutes: number;
	media_processing_interval_hours: number;
	include_podcasts_in_digest: boolean;
	include_youtube_in_digest: boolean;
	cover_enabled: boolean;
	cover_provider: 'gpt-image-1' | 'nano-banana';
	cover_quality: 'low' | 'medium' | 'high';
	cover_prompt: string;
	cover_overlay_enabled: boolean;
	cover_openai_api_key: string;
	cover_gemini_api_key: string;
	updated_at: string;
	wallabag?: IntegrationStatus | null;
	newsletters?: IntegrationStatus | null;
}

export interface ClientConfigUpdate {
	min_word_count?: number;
	morning_hour?: number;
	morning_minute?: number;
	noon_hour?: number;
	noon_minute?: number;
	evening_hour?: number;
	evening_minute?: number;
	timezone?: string;
	newsletters_enabled?: boolean;
	whisper_provider?: string;
	whisper_model?: string;
	whisper_timeout_minutes?: number;
	media_processing_interval_hours?: number;
	include_podcasts_in_digest?: boolean;
	include_youtube_in_digest?: boolean;
	cover_enabled?: boolean;
	cover_provider?: 'gpt-image-1' | 'nano-banana';
	cover_quality?: 'low' | 'medium' | 'high';
	cover_prompt?: string;
	cover_overlay_enabled?: boolean;
	cover_openai_api_key?: string;
	cover_gemini_api_key?: string;
	client_updated_at?: string;
}

export interface ManualCover {
	id: string;
	name: string;
	media_type: string;
	size_bytes: number;
	is_active: boolean;
	created_at: string;
	preview_data_url: string;
}

export interface ManualCoversResponse {
	covers: ManualCover[];
}

// ============ Feeds ============

export type FeedMode = 'raw' | 'summarize';

export interface Feed {
	id: string;
	url: string;
	title: string;
	is_active: boolean;
	mode: FeedMode;
	max_articles: number;
	created_at: string;
	updated_at: string;
}

export interface FeedCreate {
	url: string;
	title: string;
	is_active?: boolean;
	mode?: FeedMode;
	max_articles?: number;
}

export interface FeedUpdate {
	title?: string;
	is_active?: boolean;
	mode?: FeedMode;
	max_articles?: number;
}

export interface FeedSync {
	url: string;
	title: string;
	is_active: boolean;
	mode: FeedMode;
	max_articles: number;
}

export interface SyncResponse {
	synced: number;
	created: number;
	updated: number;
	unchanged: number;
}

export interface FeedCheckResponse {
	feed_type: 'article' | 'podcast' | 'youtube';
}

// ============ Digests ============

export type DigestStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type DigestPeriod = 'morning' | 'noon' | 'evening' | 'manual';

export interface Digest {
	id: string;
	period: DigestPeriod;
	status: DigestStatus;
	stage?: string | null;
	total_feeds: number;
	feeds_fetched: number;
	total_articles: number;
	articles_enriched: number;
	filename?: string | null;
	available_formats?: string[];
	created_at: string;
	completed_at?: string | null;
	downloaded_at?: string | null;
}

export interface DigestProgress {
	total_feeds: number;
	feeds_fetched: number;
	total_articles: number;
	articles_enriched: number;
}

export interface DigestStatusResponse {
	id: string;
	status: string;
	stage: string | null;
	progress: DigestProgress;
	started_at: string;
	eta_seconds: number | null;
}

export interface DigestArticle {
	id: string;
	title: string;
	url: string;
	mode: string;
	word_count: number;
	content: string;
	content_html?: string;
	author?: string | null;
	feed_title: string;
	sort_order: number;
	ai_failed: boolean;
	content_type?: string;
}

export interface DigestArticlesResponse {
	digest_id: string;
	article_count: number;
	articles: DigestArticle[];
}

export interface DigestArticleSourceResponse {
	digest_id: string;
	article_id: string;
	url: string;
	final_url: string;
	content_type?: string | null;
	fetched_at: string;
	size_bytes: number;
	html: string;
}

export interface TriggerResponse {
	id: string | null;
	status: string;
	message: string;
}

// ============ Schedules ============

export interface Schedule {
	id: string;
	period: DigestPeriod;
	hour: number;
	minute: number;
	enabled: boolean;
	timezone: string;
	created_at: string;
	updated_at: string;
	last_run_at?: string | null;
	last_run_digest_id?: string | null;
	next_run_at?: string | null;
}

export interface ScheduleUpdate {
	hour?: number;
	minute?: number;
	enabled?: boolean;
	timezone?: string;
}

// ============ Newsletters ============

export interface NewsletterStatus {
	configured: boolean;
	oauth_ready: boolean;
	label: string;
}

// ============ Logs ============

export interface LogFileInfo {
	filename: string;
	size_bytes: number;
	modified_at: string;
}

// ============ Wallabag ============

export interface WallabagConfigResponse {
	url: string;
	client_id: string;
	client_secret: string;
	username: string;
	password: string;
	mode: 'raw' | 'summarize';
	max_articles: number;
	tag_on_process: string;
	enabled: boolean;
}

export interface WallabagConfigUpdate {
	url?: string;
	client_id?: string;
	client_secret?: string;
	username?: string;
	password?: string;
	mode?: string;
	max_articles?: number;
	tag_on_process?: string;
	enabled?: boolean;
}

export interface WallabagTestResult {
	status: 'ok' | 'error';
	detail?: string;
}

// ============ Whisper Models ============

export interface WhisperModelInfo {
	name: string;
	filename: string;
	downloaded: boolean;
	size_bytes?: number | null;
	status: 'not_downloaded' | 'downloading' | 'downloaded' | 'failed';
	bytes_downloaded?: number | null;
	total_bytes?: number | null;
	error?: string | null;
}

export interface WhisperModelsResponse {
	active_model: string;
	models: WhisperModelInfo[];
}

export interface WhisperModelRequest {
	model: string;
}

// ============ Integration Previews ============

export interface PreviewArticle {
	title: string;
	url: string;
	author?: string | null;
	word_count?: number | null;
}

export interface PreviewResponse {
	status: 'ok' | 'error';
	detail?: string;
	count: number;
	articles: PreviewArticle[];
}

// ============ Media Feeds & Items ============

export type MediaFeedType = 'podcast' | 'youtube';

export interface MediaFeed {
	id: string;
	feed_type: MediaFeedType;
	url: string;
	resolved_feed_url: string | null;
	title: string;
	is_active: boolean;
	mode: FeedMode;
	max_items: number;
	created_at: string;
	updated_at: string;
	deleted_at: string | null;
}

export interface MediaFeedCreate {
	feed_type: MediaFeedType;
	url: string;
	resolved_feed_url?: string | null;
	title: string;
	is_active?: boolean;
	mode?: FeedMode;
	max_items?: number;
}

export interface MediaFeedUpdate {
	title?: string;
	is_active?: boolean;
	mode?: FeedMode;
	max_items?: number;
}

export type MediaItemStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface MediaItem {
	id: string;
	media_feed_id: string;
	guid: string;
	url: string;
	content_url: string | null;
	title: string;
	author: string | null;
	content: string;
	content_type: string;
	mode: string;
	word_count: number;
	is_summary: boolean;
	ai_failed: boolean;
	processing_ms: number;
	status: MediaItemStatus;
	error_message: string | null;
	consumed_at: string | null;
	consumed_digest_id: string | null;
	created_at: string;
	completed_at: string | null;
}

export interface MediaItemSummary {
	id: string;
	media_feed_id: string;
	title: string;
	author: string | null;
	content_type: string;
	mode: string;
	word_count: number;
	is_summary: boolean;
	ai_failed: boolean;
	processing_ms: number;
	status: MediaItemStatus;
	error_message: string | null;
	consumed_at: string | null;
	created_at: string;
	completed_at: string | null;
}

export interface MediaProcessingRun {
	id: string;
	started_at: string;
	completed_at: string | null;
	duration_ms: number;
	status: 'running' | 'completed' | 'failed';
	items_discovered: number;
	items_processed: number;
	items_failed: number;
	error_message: string | null;
}

export interface MediaProcessingStatus {
	is_running: boolean;
	pending_count: number;
	processing_count: number;
	completed_count: number;
	failed_count: number;
	current_item_title: string | null;
	current_item_content_type: string | null;
	last_completed_at: string | null;
	next_run_at: string | null;
	last_run: MediaProcessingRun | null;
}

export interface YouTubeResolveResponse {
	rss_feed_url: string;
	channel_id: string;
	channel_title: string | null;
}

export interface MediaTriggerResponse {
	status: string;
	detail: string | null;
}

// ============ API Error ============

export interface APIError {
	detail: string | { message: string; [key: string]: unknown };
}
