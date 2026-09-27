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
