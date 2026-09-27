import { expect, test } from '@playwright/test';
import { expectNoUnexpectedRequests, mockGhostwriterApi } from './fixtures/mockApi';

test.afterEach(async ({ page }) => expectNoUnexpectedRequests(page));

test('shows auth gate and accepts valid credentials', async ({ page }) => {
	await mockGhostwriterApi(page, { authenticated: false });
	await page.goto('/');
	await expect(page.getByText('Welcome Back')).toBeVisible();
	await expect(page.locator('aside')).toHaveCount(0);
	await page.getByLabel('Username').fill('demo');
	await page.getByLabel('Password').fill('password123');
	await page.getByRole('button', { name: 'Sign In' }).click();
	await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
	await expect(page.locator('aside').getByRole('link', { name: 'Feeds' })).toBeVisible();
});

test('rejects invalid credentials and keeps the auth gate', async ({ page }) => {
	await mockGhostwriterApi(page, { authenticated: false });
	await page.goto('/');
	await page.getByLabel('Username').fill('demo');
	await page.getByLabel('Password').fill('wrong-password');
	await page.getByRole('button', { name: 'Sign In' }).click();
	await expect(page.getByText('Invalid username or password')).toBeVisible();
	await expect(page.getByText('Welcome Back')).toBeVisible();
	await expect(page.locator('aside')).toHaveCount(0);
	await expect.poll(() => page.evaluate(() => localStorage.getItem('ghostwriter_token'))).toBeNull();
});
