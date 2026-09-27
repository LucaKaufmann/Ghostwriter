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
