import { expect, test } from '@playwright/test';
import { mockGhostwriterApi, setAuthenticatedSession } from './fixtures/mockApi';

test('web feed edit preserves the intent and retries only after explicit choice', async ({ page }, testInfo) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	const submittedVersions: string[] = [];
	await page.route('**/api/feeds/feed-1', async (route) => {
		const version = route.request().headers()['if-match'];
		submittedVersions.push(version);
		if (submittedVersions.length === 1) {
			await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({
				detail: { code: 'feed_conflict', current: {
					kind: 'feed', id: 'feed-1', url: 'https://example.com/feed.xml',
					version: 4, title: 'Server title', mode: 'raw', is_active: true, max_articles: 8
				} }
			}) });
		} else {
			await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
				id: 'feed-1', version: 5, url: 'https://example.com/feed.xml',
				title: 'Server title', mode: 'raw', is_active: false, max_articles: 8,
				created_at: '2025-10-01T10:00:00Z', updated_at: '2026-02-10T10:00:00Z'
			}) });
		}
	});
	await page.goto('/sources/feeds');
	await page.getByTitle('Pause feed').first().click();
	await expect(page.getByRole('alert')).toContainText('Server title');
	await expect(page.getByRole('button', { name: 'Retry with current server version' })).toBeVisible();
	await page.screenshot({ path: testInfo.outputPath('feed-conflict.png'), fullPage: true });
	expect(submittedVersions).toEqual(['"1"']);
	await page.getByRole('button', { name: 'Retry with current server version' }).click();
	await expect.poll(() => submittedVersions).toEqual(['"1"', '"4"']);
});

test('edit and bulk feed actions send each displayed version', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	const writes: { method: string; id: string; version: string }[] = [];
	await page.route(/\/api\/feeds\/feed-[123]$/, async (route) => {
		const request = route.request();
		writes.push({ method: request.method(), id: new URL(request.url()).pathname.split('/').at(-1)!,
			version: request.headers()['if-match'] });
		await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
			status: 'deleted', id: writes.at(-1)?.id, version: 9
		}) });
	});
	await page.goto('/sources/feeds');
	const row = page.getByRole('row').filter({ hasText: 'Example Feed' });
	await row.getByRole('button').last().click();
	await page.getByRole('menuitem', { name: 'Edit' }).click();
	await page.locator('#edit-title').fill('My edit');
	await page.getByRole('button', { name: 'Save Changes' }).click();
	await expect.poll(() => writes.length).toBe(1);
	expect(writes[0]).toEqual({ method: 'PUT', id: 'feed-1', version: '"1"' });
	await page.getByLabel('Select all visible feeds').check();
	await page.getByRole('button', { name: 'Pause', exact: true }).click();
	await expect.poll(() => writes.length).toBe(4);
	expect(writes.slice(1).map((write) => write.version).sort()).toEqual(['"1"', '"2"', '"3"']);
	await page.getByRole('button', { name: 'Delete', exact: true }).click();
	await page.getByRole('button', { name: 'Delete Selected' }).click();
	await expect.poll(() => writes.length).toBe(7);
	expect(writes.slice(4).map((write) => write.version).sort()).toEqual(['"1"', '"2"', '"3"']);
});

for (const tombstone of [false, true]) {
	test(`edit dialog exposes the ${tombstone ? 'restore' : 'retry'} choice and retains its proposal`, async ({ page }, testInfo) => {
		await mockGhostwriterApi(page);
		await setAuthenticatedSession(page);
		const writes: { method: string; version: string; data: unknown }[] = [];
		await page.route(/\/api\/feeds(?:\/feed-1)?$/, async (route) => {
			if (route.request().method() === 'GET') return route.fallback();
			writes.push({ method: route.request().method(), version: route.request().headers()['if-match'], data: route.request().postDataJSON() });
			await route.fulfill({ status: writes.length === 1 ? 409 : 200, contentType: 'application/json', body: JSON.stringify(writes.length === 1 ? {
				detail: { code: 'feed_conflict', current: { kind: tombstone ? 'tombstone' : 'feed', version: 4,
					url: 'https://example.com/feed.xml', title: 'Server title', mode: 'raw', is_active: true, max_articles: 8 } }
			} : { id: 'feed-1', version: 5 }) });
		});
		await page.goto('/sources/feeds');
		await page.getByRole('row').filter({ hasText: 'Example Feed' }).getByRole('button').last().click();
		await page.getByRole('menuitem', { name: 'Edit' }).click();
		await page.locator('#edit-title').fill('My preserved proposal');
		await page.getByRole('button', { name: 'Save Changes' }).click();
		await expect(page.getByRole('dialog')).toHaveCount(0);
		await expect(page.getByRole('alert')).toContainText(tombstone ? 'deleted' : 'Server title');
		expect(writes).toHaveLength(1);
		const action = page.getByRole('button', { name: tombstone ? 'Restore feed with my changes' : 'Retry with current server version' });
		await expect(action).toBeVisible();
		if (tombstone) await page.screenshot({ path: testInfo.outputPath('deleted-feed-restore.png'), fullPage: true });
		await action.click();
		await expect.poll(() => writes.length).toBe(2);
		expect(writes[1].method).toBe(tombstone ? 'POST' : 'PUT');
		expect(writes[1].version).toBe('"4"');
		expect(writes[1].data).toMatchObject(writes[0].data as Record<string, unknown>);
		expect(writes[1].data).toMatchObject({ title: 'My preserved proposal' });
		if (tombstone) expect(writes[1].data).toMatchObject({ url: 'https://example.com/feed.xml' });
	});
}

test('add dialog closes before offering explicit versioned restoration', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	const writes: { version?: string; data: unknown }[] = [];
	await page.route('**/api/feeds', async (route) => {
		if (route.request().method() === 'GET') return route.fallback();
		writes.push({ version: route.request().headers()['if-match'], data: route.request().postDataJSON() });
		await route.fulfill({ status: writes.length === 1 ? 428 : 200, contentType: 'application/json', body: JSON.stringify(writes.length === 1
			? { detail: { code: 'feed_version_required', current: { kind: 'tombstone', version: 9 } } }
			: { id: 'restored', version: 10 }) });
	});
	await page.goto('/sources/feeds');
	await page.getByRole('button', { name: 'Add Feed', exact: true }).first().click();
	await page.locator('#url').fill('https://example.com/deleted.xml');
	await page.locator('#title').fill('Restore proposal');
	await page.getByRole('dialog').getByRole('button', { name: 'Add Feed', exact: true }).click();
	await expect(page.getByRole('dialog')).toHaveCount(0);
	expect(writes).toHaveLength(1);
	await page.getByRole('button', { name: 'Restore feed with my changes' }).click();
	await expect.poll(() => writes.length).toBe(2);
	expect(writes[1].version).toBe('"9"');
	expect(writes[1].data).toEqual(writes[0].data);
	await expect(page.getByRole('alert')).toHaveCount(0);
	await page.getByRole('button', { name: 'Add Feed', exact: true }).first().click();
	await expect(page.locator('#url')).toHaveValue('');
	await expect(page.locator('#title')).toHaveValue('');
});

test('delayed Add restoration does not clear a newer Add draft', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	let release!: () => void;
	const held = new Promise<void>((resolve) => { release = resolve; });
	let restoring = false;
	let writes = 0;
	await page.route('**/api/feeds', async (route) => {
		if (route.request().method() === 'GET') return route.fallback();
		writes += 1;
		if (writes === 1) return route.fulfill({ status: 428, contentType: 'application/json',
			body: JSON.stringify({ detail: { code: 'feed_version_required',
				current: { kind: 'tombstone', version: 9 } } }) });
		restoring = true;
		await held;
		await route.fulfill({ status: 200, contentType: 'application/json',
			body: JSON.stringify({ id: 'restored', version: 10 }) });
	});
	await page.goto('/sources/feeds');
	await page.getByRole('button', { name: 'Add Feed', exact: true }).first().click();
	await page.locator('#url').fill('https://example.com/deleted.xml');
	await page.locator('#title').fill('Restore proposal');
	await page.getByRole('dialog').getByRole('button', { name: 'Add Feed', exact: true }).click();
	await expect(page.getByRole('dialog')).toHaveCount(0);
	await page.getByRole('button', { name: 'Restore feed with my changes' }).click();
	await expect.poll(() => restoring).toBe(true);
	await page.getByRole('button', { name: 'Add Feed', exact: true }).first().click();
	await page.locator('#url').fill('https://example.com/new-draft.xml');
	await page.locator('#title').fill('Keep this new draft');
	release();
	await expect(page.getByRole('alert')).toHaveCount(0);
	await expect(page.getByRole('dialog')).toBeVisible();
	await expect(page.locator('#url')).toHaveValue('https://example.com/new-draft.xml');
	await expect(page.locator('#title')).toHaveValue('Keep this new draft');
});

test('a restore proposal survives unrelated success and a transient POST failure', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	await page.route('**/api/feeds/feed-1', async (route) => route.fulfill({
		status: 409, contentType: 'application/json', body: JSON.stringify({
			detail: { code: 'feed_conflict', current: { kind: 'tombstone', version: 4 } }
		})
	}));
	await page.route('**/api/feeds/feed-2', async (route) => route.fulfill({
		status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'feed-2', version: 5 })
	}));
	const restores: unknown[] = [];
	await page.route('**/api/feeds', async (route) => {
		if (route.request().method() === 'GET') return route.fallback();
		restores.push(route.request().postDataJSON());
		await route.fulfill({ status: restores.length === 1 ? 500 : 200,
			contentType: 'application/json', body: JSON.stringify(restores.length === 1
				? { detail: 'Temporary failure' } : { id: 'feed-1', version: 5 }) });
	});
	await page.goto('/sources/feeds');
	await page.getByRole('row').filter({ hasText: 'Example Feed' }).getByRole('button').last().click();
	await page.getByRole('menuitem', { name: 'Edit' }).click();
	await page.locator('#edit-title').fill('Keep my proposal');
	await page.getByRole('button', { name: 'Save Changes' }).click();
	const restore = page.getByRole('button', { name: 'Restore feed with my changes' });
	await expect(restore).toBeVisible();
	await page.getByRole('row').filter({ hasText: 'Daily News' }).getByTitle('Pause feed').click();
	await expect(page.getByText('Feed paused', { exact: true })).toBeVisible();
	await expect(restore).toBeVisible();
	await restore.click();
	await expect(page.getByText('Failed to create feed', { exact: true })).toBeVisible();
	await expect(restore).toBeVisible();
	await restore.click();
	await expect.poll(() => restores.length).toBe(2);
	expect(restores[1]).toEqual(restores[0]);
	expect(restores[1]).toMatchObject({ title: 'Keep my proposal' });
	await expect(restore).toHaveCount(0);
});

test('a concurrently restored feed switches the captured proposal to guarded update', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	const writes: { method: string; version?: string; data: unknown }[] = [];
	await page.route(/\/api\/feeds(?:\/feed-1)?$/, async (route) => {
		if (route.request().method() === 'GET') return route.fallback();
		writes.push({ method: route.request().method(), version: route.request().headers()['if-match'], data: route.request().postDataJSON() });
		const current = writes.length === 1 ? { kind: 'tombstone', version: 4 } : {
			kind: 'feed', id: 'feed-1', version: 5, title: 'Other restoration', mode: 'raw', is_active: true, max_articles: 3
		};
		await route.fulfill({ status: writes.length < 3 ? 409 : 200, contentType: 'application/json',
			body: JSON.stringify(writes.length < 3 ? { detail: { code: 'feed_conflict', current } } : { id: 'feed-1', version: 6 }) });
	});
	await page.goto('/sources/feeds');
	await page.getByRole('row').filter({ hasText: 'Example Feed' }).getByRole('button').last().click();
	await page.getByRole('menuitem', { name: 'Edit' }).click();
	await page.locator('#edit-title').fill('Captured title');
	await page.getByRole('button', { name: 'Save Changes' }).click();
	await page.getByRole('button', { name: 'Restore feed with my changes' }).click();
	await expect(page.getByRole('alert')).toContainText('Other restoration');
	await expect(page.getByRole('button', { name: 'Restore feed with my changes' })).toHaveCount(0);
	expect(writes).toHaveLength(2);
	await page.getByRole('button', { name: 'Retry with current server version' }).click();
	await expect.poll(() => writes.length).toBe(3);
	expect(writes.map((x) => x.method)).toEqual(['PUT', 'POST', 'PUT']);
	expect(writes[2].version).toBe('"5"');
	expect(writes[2].data).toEqual(writes[0].data);
});

test('partial status retries restore from the latest active snapshot after a tombstone', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	const writes: { method: string; version?: string; data: Record<string, unknown> }[] = [];
	await page.route(/\/api\/feeds(?:\/feed-1)?$/, async (route) => {
		if (route.request().method() === 'GET') return route.fallback();
		writes.push({ method: route.request().method(), version: route.request().headers()['if-match'],
			data: route.request().postDataJSON() });
		const current = writes.length === 1
			? { kind: 'feed', id: 'feed-1', version: 4, title: 'Latest server title',
				mode: 'raw', is_active: true, max_articles: 17 }
			: { kind: 'tombstone', version: 5 };
		await route.fulfill({ status: writes.length < 3 ? 409 : 200, contentType: 'application/json',
			body: JSON.stringify(writes.length < 3 ? { detail: { code: 'feed_conflict', current } } :
				{ id: 'feed-1', version: 6 }) });
	});
	await page.goto('/sources/feeds');
	await page.getByTitle('Pause feed').first().click();
	await page.getByRole('button', { name: 'Retry with current server version' }).click();
	await expect(page.getByRole('button', { name: 'Restore feed with my changes' })).toBeVisible();
	await page.getByRole('button', { name: 'Restore feed with my changes' }).click();
	await expect.poll(() => writes.length).toBe(3);
	expect(writes[2]).toMatchObject({ method: 'POST', version: '"5"', data: {
		url: 'https://example.com/feed.xml', title: 'Latest server title',
		mode: 'raw', is_active: false, max_articles: 17
	} });
});

test('a second active conflict refreshes the later tombstone restore payload', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	const writes: { method: string; data: Record<string, unknown> }[] = [];
	await page.route(/\/api\/feeds(?:\/feed-1)?$/, async (route) => {
		if (route.request().method() === 'GET') return route.fallback();
		writes.push({ method: route.request().method(), data: route.request().postDataJSON() });
		const current = [
			{ kind: 'feed', id: 'feed-1', version: 4, title: 'First server edit', mode: 'raw', is_active: true, max_articles: 12 },
			{ kind: 'tombstone', version: 5 },
			{ kind: 'feed', id: 'feed-1', version: 6, title: 'Latest server edit', mode: 'summarize', is_active: true, max_articles: 23 },
			{ kind: 'tombstone', version: 7 }
		][writes.length - 1];
		await route.fulfill({ status: writes.length < 5 ? 409 : 200, contentType: 'application/json',
			body: JSON.stringify(writes.length < 5 ? { detail: { code: 'feed_conflict', current } } :
				{ id: 'feed-1', version: 8 }) });
	});
	await page.goto('/sources/feeds');
	await page.getByTitle('Pause feed').first().click();
	for (const name of ['Retry with current server version', 'Restore feed with my changes',
		'Retry with current server version', 'Restore feed with my changes']) {
		await page.getByRole('button', { name }).click();
	}
	await expect.poll(() => writes.length).toBe(5);
	expect(writes[4]).toMatchObject({ method: 'POST', data: {
		title: 'Latest server edit', mode: 'summarize', max_articles: 23, is_active: false
	} });
});

test('concurrent conflicts retain both proposals until each is resolved', async ({ page }, testInfo) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	const writes: Record<string, number> = {};
	await page.route(/\/api\/feeds\/feed-[12]$/, async (route) => {
		const id = new URL(route.request().url()).pathname.split('/').at(-1)!;
		writes[id] = (writes[id] ?? 0) + 1;
		await route.fulfill({ status: writes[id] === 1 ? 409 : 200, contentType: 'application/json',
			body: JSON.stringify(writes[id] === 1 ? { detail: { code: 'feed_conflict', current: {
				kind: 'feed', id, version: 8, title: `${id} changed`, mode: 'raw',
				is_active: true, max_articles: 8
			} } } : { id, version: 9 }) });
	});
	await page.goto('/sources/feeds');
	await page.getByRole('row').filter({ hasText: 'Example Feed' }).getByRole('button').last().click();
	await page.getByRole('menuitem', { name: 'Edit' }).click();
	await page.locator('#edit-title').fill('First proposal');
	await page.getByRole('button', { name: 'Save Changes' }).click();
	await expect(page.getByRole('alert')).toHaveCount(1);
	await page.getByRole('row').filter({ hasText: 'Daily News' }).getByTitle('Pause feed').click();
	await expect(page.getByRole('alert')).toHaveCount(2);
	await page.screenshot({ path: testInfo.outputPath('two-feed-conflicts.png'), fullPage: true });
	await page.getByRole('alert').nth(1).getByRole('button', { name: 'Retry with current server version' }).click();
	await expect(page.getByRole('alert')).toHaveCount(1);
	await expect(page.getByRole('alert').first()).toContainText('feed-1 changed');
	await page.getByRole('alert').first().getByRole('button', { name: 'Retry with current server version' }).click();
	await expect(page.getByRole('alert')).toHaveCount(0);
	expect(writes).toMatchObject({ 'feed-1': 2, 'feed-2': 2 });
});

test('bulk tombstone conflicts identify each feed beside its Restore action', async ({ page }, testInfo) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	await page.route(/\/api\/feeds\/feed-[12]$/, async (route) => route.fulfill({
		status: 409, contentType: 'application/json', body: JSON.stringify({
			detail: { code: 'feed_conflict', current: { kind: 'tombstone', version: 9 } }
		})
	}));
	await page.goto('/sources/feeds');
	await page.getByLabel('Select Example Feed').first().check();
	await page.getByLabel('Select Daily News').first().check();
	await page.getByRole('button', { name: 'Pause', exact: true }).click();
	await expect(page.getByRole('alert')).toHaveCount(2);
	await expect(page.getByRole('alert').filter({ hasText: 'Example Feed' })).toContainText('https://example.com/feed.xml');
	await expect(page.getByRole('alert').filter({ hasText: 'Daily News' })).toContainText('https://news.example.org/rss');
	for (const alert of await page.getByRole('alert').all()) {
		await expect(alert.getByRole('button', { name: 'Restore feed with my changes' })).toBeVisible();
	}
	await page.screenshot({ path: testInfo.outputPath('identified-tombstone-conflicts.png'), fullPage: true });
});

test('empty-state Add reopening protects its new draft from a delayed submit', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	let release!: () => void;
	const held = new Promise<void>((resolve) => { release = resolve; });
	let submitted = false;
	await page.route('**/api/feeds', async (route) => {
		if (route.request().method() === 'GET') return route.fulfill({
			status: 200, contentType: 'application/json', body: '[]'
		});
		submitted = true;
		await held;
		await route.fulfill({ status: 200, contentType: 'application/json',
			body: JSON.stringify({ id: 'new-feed', version: 1 }) });
	});
	await page.goto('/sources/feeds');
	await expect(page.getByText('No feeds yet')).toBeVisible();
	await page.getByRole('button', { name: 'Add Feed', exact: true }).last().click();
	await page.locator('#url').fill('https://example.com/first.xml');
	await page.locator('#title').fill('First submission');
	await page.getByRole('dialog').getByRole('button', { name: 'Add Feed', exact: true }).click();
	await expect.poll(() => submitted).toBe(true);
	await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
	await page.getByRole('button', { name: 'Add Feed', exact: true }).last().click();
	await page.locator('#url').fill('https://example.com/new-draft.xml');
	await page.locator('#title').fill('Keep this new draft');
	release();
	await expect(page.getByText('Feed saved successfully')).toBeVisible();
	await expect(page.getByRole('dialog')).toBeVisible();
	await expect(page.locator('#url')).toHaveValue('https://example.com/new-draft.xml');
	await expect(page.locator('#title')).toHaveValue('Keep this new draft');
});

test('delayed status conflict leaves an unrelated edit form and draft open', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	let release!: () => void;
	const held = new Promise<void>((resolve) => { release = resolve; });
	let received = false;
	await page.route('**/api/feeds/feed-1', async (route) => {
		received = true;
		await held;
		await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({
			detail: { code: 'feed_conflict', current: { kind: 'feed', version: 4,
				title: 'Server title', mode: 'raw', is_active: true, max_articles: 8 } }
		}) });
	});
	await page.goto('/sources/feeds');
	await page.getByTitle('Pause feed').first().click();
	await expect.poll(() => received).toBe(true);
	await page.getByRole('row').filter({ hasText: 'Daily News' }).getByRole('button').last().click();
	await page.getByRole('menuitem', { name: 'Edit' }).click();
	await page.locator('#edit-title').fill('Unsent second feed edit');
	release();
	await expect(page.getByRole('alert')).toHaveCount(1);
	await expect(page.getByRole('dialog')).toBeVisible();
	await expect(page.locator('#edit-title')).toHaveValue('Unsent second feed edit');
});

test('an older delayed conflict cannot replace a newer edit proposal', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	let releaseOlder!: () => void;
	const heldOlder = new Promise<void>((resolve) => { releaseOlder = resolve; });
	let olderReceived = false;
	await page.route(/\/api\/feeds\/feed-[12]$/, async (route) => {
		const id = new URL(route.request().url()).pathname.split('/').at(-1)!;
		if (id === 'feed-1') {
			olderReceived = true;
			await heldOlder;
		}
		await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({
			detail: { code: 'feed_conflict', current: { kind: 'feed', id, version: 7,
				title: `${id} server`, mode: 'raw', is_active: true, max_articles: 5 } }
		}) });
	});
	await page.goto('/sources/feeds');
	await page.getByTitle('Pause feed').first().click();
	await expect.poll(() => olderReceived).toBe(true);
	await page.getByRole('row').filter({ hasText: 'Daily News' }).getByRole('button').last().click();
	await page.getByRole('menuitem', { name: 'Edit' }).click();
	await page.locator('#edit-title').fill('Newer preserved edit');
	await page.getByRole('button', { name: 'Save Changes' }).click();
	await expect(page.getByRole('alert')).toHaveCount(1);
	await expect(page.getByRole('alert')).toContainText('feed-2 server');
	releaseOlder();
	await expect(page.getByRole('alert')).toHaveCount(2);
	await expect(page.getByRole('alert').first()).toContainText('feed-2 server');
	await expect(page.getByRole('alert').last()).toContainText('feed-1 server');
});

test('a delayed edit conflict preserves typing after submission and retries the submitted proposal', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	let release!: () => void;
	const held = new Promise<void>((resolve) => { release = resolve; });
	const writes: { title: string; version: string }[] = [];
	await page.route('**/api/feeds/feed-1', async (route) => {
		writes.push({ title: route.request().postDataJSON().title, version: route.request().headers()['if-match'] });
		if (writes.length === 1) {
			await held;
			await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({
				detail: { code: 'feed_conflict', current: { kind: 'feed', id: 'feed-1', version: 4,
					title: 'Server title', mode: 'raw', is_active: true, max_articles: 8 } }
			}) });
		} else {
			await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'feed-1', version: 5 }) });
		}
	});
	await page.goto('/sources/feeds');
	await page.getByRole('row').filter({ hasText: 'Example Feed' }).getByRole('button').last().click();
	await page.getByRole('menuitem', { name: 'Edit' }).click();
	await page.locator('#edit-title').fill('Submitted edit');
	await page.getByRole('button', { name: 'Save Changes' }).click();
	await expect.poll(() => writes.length).toBe(1);
	await page.locator('#edit-title').fill('Later unsent edit');
	release();
	await expect(page.getByRole('alert')).toContainText('Server title');
	await expect(page.getByRole('dialog')).toBeVisible();
	await expect(page.locator('#edit-title')).toHaveValue('Later unsent edit');
	await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
	await page.getByRole('button', { name: 'Retry with current server version' }).click();
	await expect.poll(() => writes.length).toBe(2);
	expect(writes).toEqual([
		{ title: 'Submitted edit', version: '"1"' },
		{ title: 'Submitted edit', version: '"4"' }
	]);
});

test('a delayed successful edit does not close a newer draft in the same session', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	let release!: () => void;
	const held = new Promise<void>((resolve) => { release = resolve; });
	let received = false;
	await page.route('**/api/feeds/feed-1', async (route) => {
		received = true;
		await held;
		await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'feed-1', version: 2 }) });
	});
	await page.goto('/sources/feeds');
	await page.getByRole('row').filter({ hasText: 'Example Feed' }).getByRole('button').last().click();
	await page.getByRole('menuitem', { name: 'Edit' }).click();
	await page.locator('#edit-title').fill('Submitted edit');
	await page.getByRole('button', { name: 'Save Changes' }).click();
	await expect.poll(() => received).toBe(true);
	await page.locator('#edit-title').fill('Later unsent edit');
	release();
	await expect(page.getByText('Feed updated successfully')).toBeVisible();
	await expect(page.getByRole('dialog')).toBeVisible();
	await expect(page.locator('#edit-title')).toHaveValue('Later unsent edit');
});

test('a late completion for edit A leaves an unrelated edit B open', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	let release!: () => void;
	const held = new Promise<void>((resolve) => { release = resolve; });
	let received = false;
	await page.route('**/api/feeds/feed-1', async (route) => {
		received = true;
		await held;
		await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'feed-1', version: 2 }) });
	});
	await page.goto('/sources/feeds');
	await page.getByRole('row').filter({ hasText: 'Example Feed' }).getByRole('button').last().click();
	await page.getByRole('menuitem', { name: 'Edit' }).click();
	await page.locator('#edit-title').fill('Edit A');
	await page.getByRole('button', { name: 'Save Changes' }).click();
	await expect.poll(() => received).toBe(true);
	await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click();
	await page.getByRole('row').filter({ hasText: 'Daily News' }).getByRole('button').last().click();
	await page.getByRole('menuitem', { name: 'Edit' }).click();
	await page.locator('#edit-title').fill('Unsent edit B');
	release();
	await expect(page.getByText('Feed updated successfully')).toBeVisible();
	await expect(page.getByRole('dialog')).toBeVisible();
	await expect(page.locator('#edit-title')).toHaveValue('Unsent edit B');
});

test('delayed restore keeps an unrelated Add submission actionable', async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
	await page.route('**/api/feeds/feed-1', async (route) => route.fulfill({
		status: 409, contentType: 'application/json', body: JSON.stringify({
			detail: { code: 'feed_conflict', current: { kind: 'tombstone', version: 4 } }
		})
	}));
	let release!: () => void;
	const held = new Promise<void>((resolve) => { release = resolve; });
	let restoring = false;
	let added = false;
	await page.route('**/api/feeds', async (route) => {
		if (route.request().method() === 'GET') return route.fallback();
		const data = route.request().postDataJSON();
		const isRestore = data.url === 'https://example.com/feed.xml';
		if (isRestore) {
			restoring = true;
			await held;
		} else {
			added = true;
		}
		await route.fulfill({ status: 200, contentType: 'application/json',
			body: JSON.stringify({ id: isRestore ? 'feed-1' : 'new-feed', version: 5 }) });
	});
	await page.goto('/sources/feeds');
	await page.getByRole('row').filter({ hasText: 'Example Feed' }).getByRole('button').last().click();
	await page.getByRole('menuitem', { name: 'Edit' }).click();
	await page.locator('#edit-title').fill('Restore edit');
	await page.getByRole('button', { name: 'Save Changes' }).click();
	await page.getByRole('button', { name: 'Restore feed with my changes' }).click();
	await expect.poll(() => restoring).toBe(true);
	await page.getByRole('button', { name: 'Add Feed', exact: true }).first().click();
	await page.locator('#url').fill('https://example.com/new-draft.xml');
	await page.locator('#title').fill('Keep this Add draft');
	const addSubmit = page.getByRole('dialog').getByRole('button', { name: 'Add Feed', exact: true });
	await expect(addSubmit).toBeEnabled();
	await expect(addSubmit).toHaveText('Add Feed');
	await addSubmit.click();
	await expect.poll(() => added).toBe(true);
	await expect(page.getByRole('dialog')).toHaveCount(0);
	await expect(page.getByRole('button', { name: 'Restore feed with my changes' })).toBeVisible();
	release();
	await expect(page.getByRole('alert')).toHaveCount(0);
	await expect(page.getByRole('dialog')).toHaveCount(0);
});
