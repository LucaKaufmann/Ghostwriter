import type { Page, Route } from '@playwright/test';

const AUTH_TOKEN = 'playwright-token';

const demoUser = {
	id: 'user-1',
	username: 'demo',
	email: 'demo@example.com',
	is_admin: true,
	created_at: '2025-01-01T00:00:00Z',
	last_login_at: '2026-02-13T09:00:00Z'
};

const feeds = [
	{
		id: 'feed-1',
		url: 'https://example.com/feed.xml',
		title: 'Example Feed',
		is_active: true,
		mode: 'summarize',
		max_articles: 8,
		created_at: '2025-10-01T10:00:00Z',
		updated_at: '2026-02-10T10:00:00Z'
	},
	{
		id: 'feed-2',
		url: 'https://news.example.org/rss',
		title: 'Daily News',
		is_active: true,
		mode: 'raw',
		max_articles: 5,
		created_at: '2025-10-02T10:00:00Z',
		updated_at: '2026-02-10T10:00:00Z'
	},
	{
		id: 'feed-3',
		url: 'https://updates.example.net/atom.xml',
		title: 'Product Updates',
		is_active: false,
		mode: 'summarize',
		max_articles: 4,
		created_at: '2025-10-03T10:00:00Z',
		updated_at: '2026-02-10T10:00:00Z'
	}
];

const digests = Array.from({ length: 36 }, (_, index) => {
	const createdAt = new Date(Date.UTC(2025, 11, 31 - index, 12, 0, 0));
	const completedAt = new Date(createdAt.getTime() + 5 * 60 * 1000);
	const period = ['morning', 'noon', 'evening', 'manual'][index % 4] as
		| 'morning'
		| 'noon'
		| 'evening'
		| 'manual';
	const failed = index % 9 === 0;
	return {
		id: `digest-${index + 1}`,
		period,
		status: failed ? 'failed' : 'completed',
		stage: failed ? 'enrichment_failed' : null,
		total_feeds: 3,
		feeds_fetched: 3,
		total_articles: failed ? 0 : 12 + (index % 8),
		articles_enriched: failed ? 0 : 12 + (index % 8),
		filename: failed ? null : `digest-${index + 1}.epub`,
		created_at: createdAt.toISOString(),
		completed_at: failed ? null : completedAt.toISOString(),
		downloaded_at: null
	};
});

function json(route: Route, data: unknown, status = 200) {
	return route.fulfill({
		status,
		contentType: 'application/json',
		body: JSON.stringify(data)
	});
}

function getDigestSubset(url: URL) {
	const limit = Number(url.searchParams.get('limit') ?? '20');
	const offset = Number(url.searchParams.get('offset') ?? '0');
	const status = url.searchParams.get('status');
	const period = url.searchParams.get('period');
	const since = url.searchParams.get('since');

	let filtered = [...digests];
	if (status) {
		filtered = filtered.filter((digest) => digest.status === status);
	}
	if (period) {
		filtered = filtered.filter((digest) => digest.period === period);
	}
	if (since) {
		const sinceTime = new Date(since).getTime();
		filtered = filtered.filter((digest) => new Date(digest.created_at).getTime() >= sinceTime);
	}

	return filtered.slice(offset, offset + limit);
}

export async function setAuthenticatedSession(page: Page) {
	await page.addInitScript(
		([key, value]) => {
			window.localStorage.setItem(key, value);
		},
		['ghostwriter_token', AUTH_TOKEN]
	);
}

export async function mockGhostwriterApi(
	page: Page,
	options: {
		authenticated?: boolean;
	} = {}
) {
	const authenticated = options.authenticated ?? true;

	await page.route('**/api/**', async (route) => {
		const request = route.request();
		const url = new URL(request.url());
		const method = request.method();
		const path = url.pathname.replace(/^\/api/, '');

		if (method === 'GET' && path === '/health') {
			return json(route, {
				status: 'ok',
				version: '0.9.0-test',
				uptime_seconds: 123456,
				last_successful_digest: '2026-02-12T09:05:00Z',
				ai_provider: 'openai',
				ai_model: 'gpt-4.1-mini',
				ai_status: 'ok'
			});
		}

		if (method === 'GET' && path === '/health/config') {
			return json(route, {
				timezone: 'UTC',
				ai_provider: 'openai',
				ai_model: 'gpt-4.1-mini',
				schedule_enabled: true,
				schedule_morning: '08:00',
				schedule_noon: '12:00',
				schedule_evening: '18:00',
				digest_retention_days: 30,
				max_articles_per_digest: 20,
				wallabag: { enabled: true, label: 'Saved' },
				newsletters: { enabled: true, label: 'Ghostwriter' }
			});
		}

		if (method === 'GET' && path === '/auth/status') {
			return json(route, {
				setup_complete: true,
				registration_open: false
			});
		}

		if (method === 'GET' && path === '/auth/me') {
			if (!authenticated) {
				return json(route, { detail: 'Unauthorized' }, 401);
			}
			return json(route, demoUser);
		}

		if (method === 'POST' && path === '/auth/login') {
			return json(route, {
				access_token: AUTH_TOKEN,
				token_type: 'bearer',
				user: demoUser
			});
		}

		if (method === 'GET' && path === '/feeds') {
			return json(route, feeds);
		}

		if (method === 'GET' && path === '/digests') {
			return json(route, getDigestSubset(url));
		}

		if (method === 'POST' && path === '/digests/trigger') {
			return json(route, {
				id: 'digest-triggered',
				status: 'accepted',
				message: 'Digest queued'
			});
		}

		if (method === 'GET' && path === '/schedules') {
			return json(route, [
				{
					id: 'schedule-morning',
					period: 'morning',
					hour: 8,
					minute: 0,
					enabled: false,
					timezone: 'UTC',
					created_at: '2025-10-01T00:00:00Z',
					updated_at: '2026-02-10T00:00:00Z',
					last_run_at: null,
					last_run_digest_id: null,
					next_run_at: null
				},
				{
					id: 'schedule-noon',
					period: 'noon',
					hour: 12,
					minute: 0,
					enabled: false,
					timezone: 'UTC',
					created_at: '2025-10-01T00:00:00Z',
					updated_at: '2026-02-10T00:00:00Z',
					last_run_at: null,
					last_run_digest_id: null,
					next_run_at: null
				},
				{
					id: 'schedule-evening',
					period: 'evening',
					hour: 18,
					minute: 0,
					enabled: false,
					timezone: 'UTC',
					created_at: '2025-10-01T00:00:00Z',
					updated_at: '2026-02-10T00:00:00Z',
					last_run_at: null,
					last_run_digest_id: null,
					next_run_at: null
				}
			]);
		}

		if (method === 'GET' && path === '/config') {
			return json(route, {
				min_word_count: 250,
				morning_hour: 8,
				morning_minute: 0,
				noon_hour: 12,
				noon_minute: 0,
				evening_hour: 18,
				evening_minute: 0,
				timezone: 'UTC',
				whisper_provider: 'faster-whisper',
				whisper_model: 'base',
				whisper_timeout_minutes: 15,
				updated_at: '2026-02-10T00:00:00Z',
				wallabag: { enabled: true, label: 'Saved' },
				newsletters: { enabled: true, label: 'Ghostwriter' }
			});
		}

		if (method === 'GET' && path === '/auth/tokens') {
			return json(route, []);
		}

		if (method === 'GET' && path === '/logs') {
			return json(route, []);
		}

		if (method === 'GET' && path === '/config/wallabag') {
			return json(route, {
				url: 'https://wallabag.example.com',
				client_id: 'client-id',
				client_secret: 'client-secret',
				username: 'demo',
				password: 'secret',
				mode: 'summarize',
				max_articles: 10,
				tag_on_process: 'ghostwriter',
				enabled: true
			});
		}

		if (method === 'GET' && path === '/config/whisper/models') {
			return json(route, {
				active_model: 'base',
				models: [
					{
						name: 'base',
						filename: 'ggml-base.bin',
						downloaded: true,
						size_bytes: 148_000_000,
						status: 'downloaded',
						bytes_downloaded: 148_000_000,
						total_bytes: 148_000_000,
						error: null
					}
				]
			});
		}

		if (method === 'GET' && path === '/newsletters/status') {
			return json(route, {
				configured: false,
				oauth_ready: true,
				label: 'Ghostwriter'
			});
		}

		if (method === 'POST' && path === '/auth/logout') {
			return route.fulfill({ status: 204, body: '' });
		}

		return json(route, { detail: `Unhandled mock route: ${method} ${path}` }, 404);
	});
}
