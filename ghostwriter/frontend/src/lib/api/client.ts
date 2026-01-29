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
	TriggerResponse,
	Schedule,
	ScheduleUpdate,
	NewsletterStatus,
	WallabagConfigResponse,
	WallabagConfigUpdate,
	WallabagTestResult,
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
	LogFileInfo
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

	// ============ Health & Config ============

	async getHealth(): Promise<HealthResponse> {
		// Health endpoint doesn't need auth
		const response = await fetch(`${BASE_URL}/health`);
		if (!response.ok) throw new ApiError(response.status, { detail: 'Health check failed' });
		return response.json();
	}

	async getPublicConfig(): Promise<ConfigResponse> {
		// Config endpoint doesn't need auth
		const response = await fetch(`${BASE_URL}/config`);
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

	async syncFeeds(feeds: FeedSync[]): Promise<SyncResponse> {
		return this.request<SyncResponse>('/feeds/sync', {
			method: 'POST',
			body: JSON.stringify(feeds)
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

	getDigestDownloadUrl(filename: string): string {
		const token = this.getToken();
		// Construct the download URL with auth
		return `${BASE_URL}/digests/${filename}${token ? `?api_key=${token}` : ''}`;
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

	// ============ Logs ============

	async getLogFiles(): Promise<LogFileInfo[]> {
		return this.request<LogFileInfo[]>('/logs');
	}

	getLogDownloadUrl(filename: string): string {
		const token = this.getToken();
		return `${BASE_URL}/logs/${filename}${token ? `?api_key=${token}` : ''}`;
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
