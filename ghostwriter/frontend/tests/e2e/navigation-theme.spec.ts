import { expect, test, type Page } from '@playwright/test';
import { mockGhostwriterApi, setAuthenticatedSession } from './fixtures/mockApi';

type RouteSpec = {
	path: string;
	heading: string;
	snapshotKey: string;
};

const coreRoutes: RouteSpec[] = [
	{ path: '/', heading: 'Dashboard', snapshotKey: 'dashboard' },
	{ path: '/feeds', heading: 'Feeds', snapshotKey: 'feeds' },
	{ path: '/digests', heading: 'Digests', snapshotKey: 'digests' },
	{ path: '/settings', heading: 'Settings', snapshotKey: 'settings' }
];

async function setTheme(page: Page, label: 'Light' | 'Dark') {
	await page.evaluate((mode) => {
		const root = document.documentElement;
		const isDark = mode === 'dark';
		root.classList.toggle('dark', isDark);
		root.style.colorScheme = isDark ? 'dark' : 'light';
	}, label.toLowerCase());
	await page.waitForTimeout(100);
}

async function goToSection(page: Page, route: RouteSpec) {
	await page.locator(`aside a[href=\"${route.path}\"]`).first().click();
	await page.waitForURL(`**${route.path === '/' ? '/' : route.path}`);
}

test.beforeEach(async ({ page }) => {
	await mockGhostwriterApi(page, { authenticated: true });
	await setAuthenticatedSession(page);
});

test('supports core route navigation', async ({ page }) => {
	await page.goto('/');
	await expect(page.locator('main').getByRole('heading', { name: 'Dashboard' })).toBeVisible();

	await expect(page.getByRole('link', { name: 'Feeds' }).first()).toHaveAttribute('href', '/feeds');
	await expect(page.getByRole('link', { name: 'Digests' }).first()).toHaveAttribute('href', '/digests');
	await expect(page.getByRole('link', { name: 'Settings' }).first()).toHaveAttribute('href', '/settings');

	for (const route of coreRoutes.slice(1)) {
		await goToSection(page, route);
		await expect(page.locator('main').getByRole('heading', { name: route.heading })).toBeVisible();
	}
});

test('captures light and dark snapshots for critical routes', async ({ page }) => {
	test.setTimeout(120_000);

	await page.goto('/');
	await expect(page.locator('main').getByRole('heading', { name: 'Dashboard' })).toBeVisible();

	for (const route of coreRoutes) {
		if (route.heading !== 'Dashboard') {
			await goToSection(page, route);
		}
		await expect(page.locator('main').getByRole('heading', { name: route.heading })).toBeVisible();

		await setTheme(page, 'Light');
		await expect(page).toHaveScreenshot(`${route.snapshotKey}-light.png`, {
			fullPage: true,
			animations: 'disabled'
		});

		await setTheme(page, 'Dark');
		await expect(page).toHaveScreenshot(`${route.snapshotKey}-dark.png`, {
			fullPage: true,
			animations: 'disabled'
		});
	}
});
