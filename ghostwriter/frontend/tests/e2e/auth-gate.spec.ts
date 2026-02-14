import { expect, test } from '@playwright/test';
import { mockGhostwriterApi } from './fixtures/mockApi';

test('shows auth gate and supports credential login', async ({ page }) => {
	await mockGhostwriterApi(page, { authenticated: false });

	await page.goto('/');

	await expect(page.getByText('Welcome Back')).toBeVisible();
	await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();

	await page.getByLabel('Username').fill('demo');
	await page.getByLabel('Password').fill('password123');
	await page.getByRole('button', { name: 'Sign In' }).click();

	await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
});
