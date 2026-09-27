import { expect, type Page, type Route } from '@playwright/test';

const AUTH_TOKEN = 'playwright-token';
const unexpectedRequests = new WeakMap<Page, string[]>();

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
	const unexpected: string[] = [];
	unexpectedRequests.set(page, unexpected);

	await page.route('**/*', async (route) => {
		const request = route.request();
		const url = new URL(request.url());
		const method = request.method();
		if (url.origin !== 'http://127.0.0.1:4173') {
			unexpected.push(`${method} ${url.origin}${url.pathname}`);
			return route.abort();
		}
		if (!url.pathname.startsWith('/api/')) {
			return route.continue();
		}
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
			const credentials = request.postDataJSON() as { username?: string; password?: string };
			if (credentials.username !== 'demo' || credentials.password !== 'password123') {
				return json(route, { detail: 'Invalid username or password' }, 401);
			}
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

		if (method === 'GET' && /^\/digests\/digest-\d+\/cover$/.test(path)) {
			return json(route, { detail: 'No cover in fixture' }, 404);
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
				media_processing_interval_hours: 6,
				include_podcasts_in_digest: false,
				include_youtube_in_digest: false,
				pdf_enabled: false,
				pdf_page_size: 'A4',
				cover_enabled: false,
				cover_provider: 'gpt-image-1',
				cover_quality: 'low',
				cover_prompt: '',
				cover_overlay_enabled: true,
				cover_openai_api_key: '',
				cover_gemini_api_key: '',
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

		if (method === 'GET' && path === '/config/covers') {
			return json(route, { covers: [], active_cover_id: null });
		}

		if (method === 'GET' && path === '/podcast/feed/info') {
			return json(route, {
				feed_enabled: false,
				feed_title: 'Ghostwriter',
				feed_description: 'Synthetic podcast feed',
				feed_url: 'http://127.0.0.1:4173/api/podcast/feed',
				setup_instructions: []
			});
		}

		if (method === 'GET' && path === '/podcast/preferences') {
			return json(route, {
				enabled: false,
				schedule: 'manual',
				schedule_time: '08:00',
				schedule_day: 'monday',
				topic_weights: {},
				boost_sources: [],
				boost_keywords: [],
				filter_keywords: [],
				preferred_length_minutes: 15,
				script_model: null,
				script_timeout_seconds: 120,
				style: 'casual',
				tts_provider: 'openai',
				openai_tts_model: 'tts-1',
				elevenlabs_model_id: '',
				elevenlabs_output_format: 'mp3_44100_128',
				elevenlabs_expressiveness: 'natural',
				host_a_voice: 'alloy',
				host_b_voice: 'nova',
				host_count: 1,
				podcast_feed_enabled: false,
				podcast_feed_title: 'Ghostwriter',
				podcast_feed_description: 'Synthetic podcast feed',
				podcast_feed_base_url: null,
				podcast_feed_artwork_path: null,
				updated_at: '2026-02-10T00:00:00Z'
			});
		}

		if (method === 'GET' && path === '/podcast/voices') {
			return json(route, { voices: [], pair_presets: [] });
		}

		if (method === 'GET' && path === '/podcast/schedules') {
			return json(route, []);
		}

		if (method === 'GET' && path === '/podcast/episodes') {
			return json(route, []);
		}

		if (method === 'GET' && path === '/media/status') {
			return json(route, {
				is_running: false,
				pending_count: 0,
				processing_count: 0,
				completed_count: 0,
				failed_count: 0,
				current_item_title: null,
				current_item_content_type: null,
				last_completed_at: null,
				next_run_at: null,
				last_run: null
			});
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

		unexpected.push(`${method} ${path}`);
		return route.abort();
	});
}

export function expectNoUnexpectedRequests(page: Page) {
	expect(unexpectedRequests.get(page) ?? []).toEqual([]);
}
