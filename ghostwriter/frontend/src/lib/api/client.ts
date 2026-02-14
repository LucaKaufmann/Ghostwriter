import type {
	HealthResponse,
	ConfigResponse,
	ClientConfigResponse,
	ClientConfigUpdate,
	Feed,
	FeedCreate,
	FeedUpdate,
	FeedSync,
	SyncResponse,
	Digest,
	DigestStatusResponse,
	DigestArticlesResponse,
	DigestArticleSourceResponse,
	TriggerResponse,
	Schedule,
	ScheduleUpdate,
	NewsletterStatus,
	WallabagConfigResponse,
	WallabagConfigUpdate,
	WallabagTestResult,
	WhisperModelsResponse,
	WhisperModelRequest,
	ManualCoversResponse,
	PreviewResponse,
	APIError,
	DigestPeriod,
	AuthStatus,
	LoginRequest,
	LoginResponse,
	RegisterRequest,
	UserResponse,
	UserUpdate,
	APITokenResponse,
	APITokenCreateRequest,
	APITokenCreateResponse,
	LogFileInfo,
	KoreaderPluginDownloadRequest,
	MediaFeed,
	MediaFeedCreate,
	MediaFeedUpdate,
	MediaItem,
	MediaItemSummary,
	MediaProcessingStatus,
	YouTubeResolveResponse,
	MediaTriggerResponse,
	FeedCheckResponse
} from './types';

// Base URL - in production, served from same origin; in dev, proxied via vite
const BASE_URL = '/api';

class ApiClient {
	private token: string | null = null;

	setToken(token: string | null) {
		this.token = token;
		if (token) {
			localStorage.setItem('ghostwriter_token', token);
		} else {
			localStorage.removeItem('ghostwriter_token');
		}
	}

	getToken(): string | null {
		if (!this.token) {
			this.token = localStorage.getItem('ghostwriter_token');
		}
		return this.token;
	}

	isAuthenticated(): boolean {
		return !!this.getToken();
	}

	private async request<T>(
		endpoint: string,
		options: RequestInit = {}
	): Promise<T> {
		const token = this.getToken();
		const headers: Record<string, string> = {
			'Content-Type': 'application/json',
			...(options.headers as Record<string, string> || {})
		};

		if (token) {
			headers['Authorization'] = `Bearer ${token}`;
		}

		const response = await fetch(`${BASE_URL}${endpoint}`, {
			...options,
			headers
		});

		if (!response.ok) {
			let error: APIError;
			try {
				error = await response.json();
			} catch {
				error = { detail: `HTTP ${response.status}: ${response.statusText}` };
			}
			throw new ApiError(response.status, error);
		}

		// Handle empty responses (204 No Content, etc.)
		const text = await response.text();
		if (!text) return {} as T;
		return JSON.parse(text);
	}

	private async download(
		endpoint: string,
		filename: string
	): Promise<{ blob: Blob; filename: string }> {
		const token = this.getToken();
		const headers: Record<string, string> = {};
		if (token) {
			headers['Authorization'] = `Bearer ${token}`;
		}

		const response = await fetch(`${BASE_URL}${endpoint}`, { headers });
		if (!response.ok) {
			let error: APIError;
			try {
				error = await response.json();
			} catch {
				error = { detail: `HTTP ${response.status}: ${response.statusText}` };
			}
			throw new ApiError(response.status, error);
		}

		const blob = await response.blob();
		return { blob, filename };
	}

	private resolveFilenameFromHeaders(headers: Headers, fallback: string): string {
		const contentDisposition = headers.get('content-disposition') || '';
		const match = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
		return match ? match[1] : fallback;
	}

	// ============ Authentication ============

	async getAuthStatus(): Promise<AuthStatus> {
		// Auth status doesn't need auth
		const response = await fetch(`${BASE_URL}/auth/status`);
		if (!response.ok) throw new ApiError(response.status, { detail: 'Auth status check failed' });
		return response.json();
	}

	async register(data: RegisterRequest): Promise<LoginResponse> {
		const response = await fetch(`${BASE_URL}/auth/register`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(data)
		});
		if (!response.ok) {
			let error: APIError;
			try {
				error = await response.json();
			} catch {
				error = { detail: `HTTP ${response.status}: ${response.statusText}` };
			}
			throw new ApiError(response.status, error);
		}
		return response.json();
	}

	async login(data: LoginRequest): Promise<LoginResponse> {
		const response = await fetch(`${BASE_URL}/auth/login`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(data)
		});
		if (!response.ok) {
			let error: APIError;
			try {
				error = await response.json();
			} catch {
				error = { detail: `HTTP ${response.status}: ${response.statusText}` };
			}
			throw new ApiError(response.status, error);
		}
		return response.json();
	}

	async logout(): Promise<void> {
		await this.request('/auth/logout', { method: 'POST' });
	}

	async getCurrentUser(): Promise<UserResponse> {
		return this.request<UserResponse>('/auth/me');
	}

	async updateCurrentUser(data: UserUpdate): Promise<UserResponse> {
		return this.request<UserResponse>('/auth/me', {
			method: 'PUT',
			body: JSON.stringify(data)
		});
	}

	// ============ API Tokens ============

	async getAPITokens(): Promise<APITokenResponse[]> {
		return this.request<APITokenResponse[]>('/auth/tokens');
	}

	async createAPIToken(data: APITokenCreateRequest): Promise<APITokenCreateResponse> {
		return this.request<APITokenCreateResponse>('/auth/tokens', {
			method: 'POST',
			body: JSON.stringify(data)
		});
	}

	async revokeAPIToken(tokenId: string): Promise<{ status: string; message: string }> {
		return this.request(`/auth/tokens/${tokenId}`, { method: 'DELETE' });
	}

	async downloadKoreaderPlugin(
		data: KoreaderPluginDownloadRequest
	): Promise<{ blob: Blob; filename: string }> {
		const token = this.getToken();
		const headers: Record<string, string> = {
			'Content-Type': 'application/json'
		};

		if (token) {
			headers['Authorization'] = `Bearer ${token}`;
		}

		const response = await fetch(`${BASE_URL}/plugins/koreader/download`, {
			method: 'POST',
			headers,
			body: JSON.stringify(data)
		});

		if (!response.ok) {
			let error: APIError;
			try {
				error = await response.json();
			} catch {
				error = { detail: `HTTP ${response.status}: ${response.statusText}` };
			}
			throw new ApiError(response.status, error);
		}

		const blob = await response.blob();
		const filename = this.resolveFilenameFromHeaders(response.headers, 'ghostwriter.koplugin.zip');
		return { blob, filename };
	}

	// ============ Health & Config ============

	async getHealth(): Promise<HealthResponse> {
		// Health endpoint doesn't need auth
		const response = await fetch(`${BASE_URL}/health`);
		if (!response.ok) throw new ApiError(response.status, { detail: 'Health check failed' });
		return response.json();
	}

	async getPublicConfig(): Promise<ConfigResponse> {
		// Config endpoint doesn't need auth
		const response = await fetch(`${BASE_URL}/health/config`);
		if (!response.ok) throw new ApiError(response.status, { detail: 'Config fetch failed' });
		return response.json();
	}

	async getClientConfig(): Promise<ClientConfigResponse> {
		return this.request<ClientConfigResponse>('/config');
	}

	async updateClientConfig(data: ClientConfigUpdate): Promise<ClientConfigResponse> {
		return this.request<ClientConfigResponse>('/config', {
			method: 'PUT',
			body: JSON.stringify(data)
		});
	}

	async getWhisperModels(): Promise<WhisperModelsResponse> {
		return this.request<WhisperModelsResponse>('/config/whisper/models');
	}

	async downloadWhisperModel(data: WhisperModelRequest): Promise<WhisperModelsResponse> {
		return this.request<WhisperModelsResponse>('/config/whisper/models/download', {
			method: 'POST',
			body: JSON.stringify(data)
		});
	}

	async deleteWhisperModel(model: string): Promise<WhisperModelsResponse> {
		return this.request<WhisperModelsResponse>(`/config/whisper/models/${model}`, {
			method: 'DELETE'
		});
	}

	async setActiveWhisperModel(data: WhisperModelRequest): Promise<WhisperModelsResponse> {
		return this.request<WhisperModelsResponse>('/config/whisper/models/active', {
			method: 'PUT',
			body: JSON.stringify(data)
		});
	}

	async listManualCovers(): Promise<ManualCoversResponse> {
		return this.request<ManualCoversResponse>('/config/covers');
	}

	async uploadManualCover(file: File): Promise<void> {
		const token = this.getToken();
		const formData = new FormData();
		formData.append('file', file);
		const headers: Record<string, string> = {};
		if (token) headers['Authorization'] = `Bearer ${token}`;

		const response = await fetch(`${BASE_URL}/config/covers/upload`, {
			method: 'POST',
			headers,
			body: formData
		});
		if (!response.ok) {
			let error: APIError;
			try {
				error = await response.json();
			} catch {
				error = { detail: `HTTP ${response.status}: ${response.statusText}` };
			}
			throw new ApiError(response.status, error);
		}
	}

	async activateManualCover(id: string): Promise<void> {
		await this.request(`/config/covers/${id}/activate`, { method: 'POST' });
	}

	async deleteManualCover(id: string): Promise<void> {
		await this.request(`/config/covers/${id}`, { method: 'DELETE' });
	}

	// ============ Feeds ============

	async getFeeds(): Promise<Feed[]> {
		return this.request<Feed[]>('/feeds');
	}

	async createFeed(data: FeedCreate): Promise<Feed> {
		return this.request<Feed>('/feeds', {
			method: 'POST',
			body: JSON.stringify(data)
		});
	}

	async getFeed(id: string): Promise<Feed> {
		return this.request<Feed>(`/feeds/${id}`);
	}

	async updateFeed(id: string, data: FeedUpdate): Promise<Feed> {
		return this.request<Feed>(`/feeds/${id}`, {
			method: 'PUT',
			body: JSON.stringify(data)
		});
	}

	async deleteFeed(id: string): Promise<{ status: string; id: string }> {
		return this.request(`/feeds/${id}`, {
			method: 'DELETE'
		});
	}

	async clearSeenArticles(id: string): Promise<{ status: string; feed_id: string; cleared_count: number }> {
		return this.request(`/feeds/${id}/clear-seen`, {
			method: 'POST'
		});
	}

	async syncFeeds(feeds: FeedSync[]): Promise<SyncResponse> {
		return this.request<SyncResponse>('/feeds/sync', {
			method: 'POST',
			body: JSON.stringify(feeds)
		});
	}

	async checkFeedUrl(url: string): Promise<FeedCheckResponse> {
		return this.request<FeedCheckResponse>('/feeds/check-url', {
			method: 'POST',
			body: JSON.stringify({ url })
		});
	}

	// ============ Digests ============

	async getDigests(params?: {
		limit?: number;
		offset?: number;
		since?: string;
		status?: string;
		period?: string;
	}): Promise<Digest[]> {
		const searchParams = new URLSearchParams();
		if (params?.limit) searchParams.set('limit', params.limit.toString());
		if (params?.offset) searchParams.set('offset', params.offset.toString());
		if (params?.since) searchParams.set('since', params.since);
		if (params?.status) searchParams.set('status', params.status);
		if (params?.period) searchParams.set('period', params.period);

		const query = searchParams.toString();
		return this.request<Digest[]>(`/digests${query ? `?${query}` : ''}`);
	}

	async getLatestDigest(): Promise<Digest> {
		return this.request<Digest>('/digests/latest');
	}

	async getDigestStatus(id: string): Promise<DigestStatusResponse> {
		return this.request<DigestStatusResponse>(`/digests/${id}/status`);
	}

	async getDigestArticles(id: string): Promise<DigestArticlesResponse> {
		return this.request<DigestArticlesResponse>(`/digests/${id}/articles`);
	}

	async getDigestArticleSource(
		digestId: string,
		articleId: string
	): Promise<DigestArticleSourceResponse> {
		return this.request<DigestArticleSourceResponse>(
			`/digests/${digestId}/articles/${articleId}/source`
		);
	}

	async triggerDigest(period: DigestPeriod = 'manual'): Promise<TriggerResponse> {
		return this.request<TriggerResponse>('/digests/trigger', {
			method: 'POST',
			body: JSON.stringify({ period })
		});
	}

	async deleteDigest(filename: string): Promise<{ status: string; filename: string }> {
		return this.request(`/digests/${filename}`, {
			method: 'DELETE'
		});
	}

	downloadDigest(filename: string): Promise<{ blob: Blob; filename: string }> {
		return this.download(`/digests/${filename}`, filename);
	}

	downloadDigestCover(digestId: string): Promise<{ blob: Blob; filename: string }> {
		return this.download(`/digests/${digestId}/cover`, `${digestId}-cover.jpg`);
	}

	// ============ Schedules ============

	async getSchedules(): Promise<Schedule[]> {
		return this.request<Schedule[]>('/schedules');
	}

	async getSchedule(period: DigestPeriod): Promise<Schedule> {
		return this.request<Schedule>(`/schedules/${period}`);
	}

	async updateSchedule(period: DigestPeriod, data: ScheduleUpdate): Promise<Schedule> {
		return this.request<Schedule>(`/schedules/${period}`, {
			method: 'PUT',
			body: JSON.stringify(data)
		});
	}

	async enableSchedule(period: DigestPeriod): Promise<Schedule> {
		return this.request<Schedule>(`/schedules/${period}/enable`, {
			method: 'POST'
		});
	}

	async disableSchedule(period: DigestPeriod): Promise<Schedule> {
		return this.request<Schedule>(`/schedules/${period}/disable`, {
			method: 'POST'
		});
	}

	async triggerSchedule(period: DigestPeriod): Promise<TriggerResponse> {
		return this.request<TriggerResponse>(`/schedules/${period}/trigger`, {
			method: 'POST'
		});
	}

	// ============ Wallabag ============

	async getWallabagConfig(): Promise<WallabagConfigResponse> {
		return this.request<WallabagConfigResponse>('/config/wallabag');
	}

	async updateWallabagConfig(data: WallabagConfigUpdate): Promise<WallabagConfigResponse> {
		return this.request<WallabagConfigResponse>('/config/wallabag', {
			method: 'PUT',
			body: JSON.stringify(data)
		});
	}

	async testWallabagConnection(): Promise<WallabagTestResult> {
		return this.request<WallabagTestResult>('/config/wallabag/test', {
			method: 'POST'
		});
	}

	async previewWallabag(): Promise<PreviewResponse> {
		return this.request<PreviewResponse>('/config/wallabag/preview', {
			method: 'POST'
		});
	}

	// ============ Newsletters ============

	async getNewsletterStatus(): Promise<NewsletterStatus> {
		return this.request<NewsletterStatus>('/newsletters/status');
	}

	getOAuthStartUrl(): string {
		return `${BASE_URL}/newsletters/oauth/start`;
	}

	async previewNewsletters(): Promise<PreviewResponse> {
		return this.request<PreviewResponse>('/newsletters/preview', {
			method: 'POST'
		});
	}

	async clearWallabagSeen(): Promise<{ cleared: number }> {
		return this.request('/config/wallabag/clear-seen', { method: 'POST' });
	}

	async clearNewsletterSeen(): Promise<{ cleared: number }> {
		return this.request('/config/newsletters/clear-seen', { method: 'POST' });
	}

	// ============ Logs ============

	async getLogFiles(): Promise<LogFileInfo[]> {
		return this.request<LogFileInfo[]>('/logs');
	}

	downloadLog(filename: string): Promise<{ blob: Blob; filename: string }> {
		return this.download(`/logs/${filename}`, filename);
	}

	// ============ Media: Podcasts ============

	async getPodcastFeeds(): Promise<MediaFeed[]> {
		return this.request<MediaFeed[]>('/media/podcasts');
	}

	async createPodcastFeed(data: MediaFeedCreate): Promise<MediaFeed> {
		return this.request<MediaFeed>('/media/podcasts', {
			method: 'POST',
			body: JSON.stringify(data)
		});
	}

	async updatePodcastFeed(id: string, data: MediaFeedUpdate): Promise<MediaFeed> {
		return this.request<MediaFeed>(`/media/podcasts/${id}`, {
			method: 'PUT',
			body: JSON.stringify(data)
		});
	}

	async deletePodcastFeed(id: string): Promise<{ status: string }> {
		return this.request(`/media/podcasts/${id}`, { method: 'DELETE' });
	}

	async getPodcastFeedItems(feedId: string): Promise<MediaItemSummary[]> {
		return this.request<MediaItemSummary[]>(`/media/podcasts/${feedId}/items`);
	}

	async getAllPodcastItems(): Promise<MediaItemSummary[]> {
		return this.request<MediaItemSummary[]>('/media/podcasts/items/all');
	}

	// ============ Media: YouTube ============

	async getYouTubeFeeds(): Promise<MediaFeed[]> {
		return this.request<MediaFeed[]>('/media/youtube');
	}

	async createYouTubeFeed(data: MediaFeedCreate): Promise<MediaFeed> {
		return this.request<MediaFeed>('/media/youtube', {
			method: 'POST',
			body: JSON.stringify(data)
		});
	}

	async updateYouTubeFeed(id: string, data: MediaFeedUpdate): Promise<MediaFeed> {
		return this.request<MediaFeed>(`/media/youtube/${id}`, {
			method: 'PUT',
			body: JSON.stringify(data)
		});
	}

	async deleteYouTubeFeed(id: string): Promise<{ status: string }> {
		return this.request(`/media/youtube/${id}`, { method: 'DELETE' });
	}

	async getYouTubeFeedItems(feedId: string): Promise<MediaItemSummary[]> {
		return this.request<MediaItemSummary[]>(`/media/youtube/${feedId}/items`);
	}

	async getAllYouTubeItems(): Promise<MediaItemSummary[]> {
		return this.request<MediaItemSummary[]>('/media/youtube/items/all');
	}

	async resolveYouTubeChannel(url: string): Promise<YouTubeResolveResponse> {
		return this.request<YouTubeResolveResponse>('/media/youtube/resolve', {
			method: 'POST',
			body: JSON.stringify({ url })
		});
	}

	// ============ Media: Shared ============

	async getMediaItem(itemId: string): Promise<MediaItem> {
		return this.request<MediaItem>(`/media/items/${itemId}`);
	}

	async triggerMediaProcessing(): Promise<MediaTriggerResponse> {
		return this.request<MediaTriggerResponse>('/media/trigger', {
			method: 'POST'
		});
	}

	async getMediaProcessingStatus(): Promise<MediaProcessingStatus> {
		return this.request<MediaProcessingStatus>('/media/status');
	}
}

export class ApiError extends Error {
	status: number;
	error: APIError;

	constructor(status: number, error: APIError) {
		const message = typeof error.detail === 'string' 
			? error.detail 
			: error.detail?.message || 'Unknown error';
		super(message);
		this.status = status;
		this.error = error;
		this.name = 'ApiError';
	}

	get isUnauthorized(): boolean {
		return this.status === 401 || this.status === 403;
	}

	get isNotFound(): boolean {
		return this.status === 404;
	}

	get isConflict(): boolean {
		return this.status === 409;
	}
}

// Singleton instance
export const api = new ApiClient();
