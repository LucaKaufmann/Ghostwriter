import { expect, test, type Page } from '@playwright/test';
import { expectNoUnexpectedRequests, mockGhostwriterApi, setAuthenticatedSession } from './fixtures/mockApi';

const expired = { detail: 'Session expired' }; // Deliberately has no status digits.

async function signIn(page: Page) {
  await page.getByLabel('Username').fill('demo');
  await page.getByLabel('Password').fill('password123');
  await page.getByRole('button', { name: 'Sign In' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
}

test.afterEach(async ({ page }) => expectNoUnexpectedRequests(page));

test('one in-session 401 ends the session, clears cached data, and permits re-login', async ({ page }) => {
  await setAuthenticatedSession(page);
  await mockGhostwriterApi(page);
  let feedRequests = 0;
  await page.route('**/api/feeds', async (route) => {
    feedRequests++;
    if (route.request().headers().authorization === 'Bearer playwright-token') {
      return route.fulfill({ status: 401, json: expired });
    }
    return route.fallback();
  });
  await page.route('**/api/auth/login', async (route) => {
    return route.fulfill({ json: {
      access_token: 'fresh-token', token_type: 'bearer',
      user: { id: 'user-2', username: 'demo', email: 'demo@example.com', is_admin: true, created_at: '2025-01-01T00:00:00Z', last_login_at: null }
    } });
  });
  await page.goto('/');
  await expect(page.getByText('Session expired. Please log in again.')).toBeVisible();
  await expect(page.getByText('Welcome Back')).toBeVisible();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ghostwriter_token'))).toBeNull();
  expect(feedRequests).toBe(1);
  await signIn(page);
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ghostwriter_token'))).toBe('fresh-token');
  await expect.poll(() => feedRequests).toBe(2); // Fetch after re-login, not old cached data.
});

test('concurrent and delayed old-token 401s cannot expire a new session', async ({ page }) => {
  await setAuthenticatedSession(page);
  await mockGhostwriterApi(page);
  let releaseOldRequest!: () => void;
  const oldRequestHeld = new Promise<void>((resolve) => { releaseOldRequest = resolve; });
  let triggerRequests = 0;
  await page.route('**/api/digests/trigger', async (route) => {
    triggerRequests++;
    if (triggerRequests === 1) await oldRequestHeld;
    await route.fulfill({ status: 401, json: expired });
  });
  await page.route('**/api/auth/login', async (route) => route.fulfill({ json: {
    access_token: 'fresh-token', token_type: 'bearer',
    user: { id: 'user-2', username: 'demo', email: 'demo@example.com', is_admin: true, created_at: '2025-01-01T00:00:00Z', last_login_at: null }
  } }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await page.locator('aside').getByRole('button', { name: 'Generate Digest' }).click();
  await expect.poll(() => triggerRequests).toBe(1);
  await page.locator('main').getByRole('button', { name: 'Generate Digest' }).click();
  await expect(page.getByText('Welcome Back')).toBeVisible();
  await signIn(page);
  const oldResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/digests/trigger') && response.status() === 401
  );
  releaseOldRequest();
  await oldResponse;
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ghostwriter_token'))).toBe('fresh-token');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  expect(triggerRequests).toBe(2);
});

test('403 leaves credentials in place and is not retried', async ({ page }) => {
  await setAuthenticatedSession(page);
  await mockGhostwriterApi(page);
  let requests = 0;
  await page.route('**/api/feeds', async (route) => {
    requests++;
    await route.fulfill({ status: 403, json: { detail: 'Forbidden' } });
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect.poll(() => requests).toBe(1);
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ghostwriter_token'))).toBe('playwright-token');
});

test('transient server failure retries within the bound without logging out', async ({ page }) => {
  await setAuthenticatedSession(page);
  await mockGhostwriterApi(page);
  let requests = 0;
  await page.route('**/api/feeds', async (route) => {
    requests++;
    if (requests < 3) return route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } });
    return route.fallback();
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect.poll(() => requests).toBe(3);
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ghostwriter_token'))).toBe('playwright-token');
});

test('network failure stops at the retry bound and keeps the credential', async ({ page }) => {
  await setAuthenticatedSession(page);
  await mockGhostwriterApi(page);
  let requests = 0;
  await page.route('**/api/feeds', async (route) => {
    requests++;
    await route.abort('failed');
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect.poll(() => requests, { timeout: 15_000 }).toBe(4);
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ghostwriter_token'))).toBe('playwright-token');
  await expect(page.getByText('Welcome Back')).toHaveCount(0);
});

test('a denied download expires the session', async ({ page }) => {
  await setAuthenticatedSession(page);
  await mockGhostwriterApi(page);
  let requests = 0;
  await page.route('**/api/digests/digest-2/download?format=epub', async (route) => {
    requests++;
    await route.fulfill({ status: 401, json: expired });
  });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Download EPUB' }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Download EPUB' }).first().click();
  await expect(page.getByText('Welcome Back')).toBeVisible();
  expect(requests).toBe(1);
});
