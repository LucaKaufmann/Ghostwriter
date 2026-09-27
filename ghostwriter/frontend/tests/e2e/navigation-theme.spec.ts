import { expect, test, type Page } from '@playwright/test';
import { expectNoUnexpectedRequests, mockGhostwriterApi, setAuthenticatedSession } from './fixtures/mockApi';

const routes = [
	{ path: '/', label: 'Dashboard', heading: 'Dashboard', snapshot: 'dashboard', content: '3 total feeds' },
	{ path: '/sources/feeds', label: 'Feeds', heading: 'Feeds', snapshot: 'feeds', content: 'Example Feed' },
	{ path: '/digests', label: 'Digests', heading: 'Digests', snapshot: 'digests', content: 'Showing' },
	{ path: '/settings', label: 'Settings', heading: 'Settings', snapshot: 'settings', content: 'openai' }
] as const;

async function selectTheme(page: Page, name: 'Light' | 'Dark') {
	await page.evaluate((theme) => {
		const dark = theme === 'Dark';
		document.documentElement.classList.toggle('dark', dark);
		document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
	}, name);
	if (name === 'Dark') {
		await expect(page.locator('html')).toHaveClass(/dark/);
	} else {
		await expect(page.locator('html')).not.toHaveClass(/dark/);
	}
}

test.beforeEach(async ({ page }) => {
	await mockGhostwriterApi(page);
	await setAuthenticatedSession(page);
});

test.afterEach(async ({ page }) => expectNoUnexpectedRequests(page));

test('sidebar uses current routes', async ({ page }) => {
	await page.goto('/');
	for (const route of routes) {
		const link = page.locator('aside').getByRole('link', { name: route.label, exact: true });
		await expect(link).toHaveAttribute('href', route.path);
		await link.click();
		await expect(page).toHaveURL(`http://127.0.0.1:4173${route.path}`);
		await expect(page.locator('main').getByRole('heading', { name: route.heading })).toBeVisible();
	}
});

test('old feeds URL redirects to source feeds', async ({ page }) => {
	await page.goto('/feeds');
	await expect(page).toHaveURL('http://127.0.0.1:4173/sources/feeds');
	await expect(page.locator('main').getByRole('heading', { name: 'Feeds' })).toBeVisible();
});

for (const route of routes) {
	test(`reviewed light and dark route snapshots: ${route.snapshot}`, async ({ page }) => {
		await page.goto(route.path);
		await expect(page.locator('main').getByRole('heading', { name: route.heading })).toBeVisible();
		await expect(page.locator('main').getByText(route.content).first()).toBeVisible();
		for (const theme of ['Light', 'Dark'] as const) {
			await selectTheme(page, theme);
			await expect(page).toHaveScreenshot(`${route.snapshot}-${theme.toLowerCase()}.png`, {
				fullPage: true,
				animations: 'disabled'
			});
		}
	});
}
