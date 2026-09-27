import { expect, test } from '@playwright/test';
import { expectNoUnexpectedRequests, mockGhostwriterApi, setAuthenticatedSession } from './fixtures/mockApi';

const routes = [
	{ path: '/', heading: 'Dashboard', content: '3 total feeds' },
	{ path: '/sources/feeds', heading: 'Feeds', content: 'Example Feed' },
	{ path: '/digests', heading: 'Digests', content: 'Showing' },
	{ path: '/settings', heading: 'Settings', content: 'openai' },
	{ path: '/episodes', heading: 'Episodes', content: 'No episodes yet' }
] as const;

test.beforeEach(async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
});

test.afterEach(async ({ page }) => expectNoUnexpectedRequests(page));

for (const route of routes) {
	test(`loads ${route.path} with fixture data`, async ({ page }) => {
		await page.goto(route.path);
		await expect(page.locator('main').getByRole('heading', { name: route.heading })).toBeVisible();
		await expect(page.locator('main').getByText(route.content).first()).toBeVisible();
	});
}
