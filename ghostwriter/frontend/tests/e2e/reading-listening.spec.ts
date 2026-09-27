import { expect, test } from '@playwright/test';
// This package deliberately does not depend on @types/node; Playwright runs in Node.
// @ts-ignore Node's built-in module is present at runtime.
import { spawn } from 'node:child_process';
// @ts-ignore Node's built-in module is present at runtime.
import { createServer } from 'node:net';
// @ts-ignore Node's built-in module is present at runtime.
import { resolve } from 'node:path';

declare const process: { env: Record<string, string | undefined>; cwd(): string };
let backend: {
  exitCode: number | null;
  kill(signal: string): void;
  once(event: string, listener: () => void): void;
};
let backendURL: string;
test.use({ trace: 'on' });

async function unusedPort(): Promise<number> {
  const server = createServer();
  await new Promise<void>((done) => server.listen(0, '127.0.0.1', done));
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('Missing fixture port');
  await new Promise<void>((done) => server.close(() => done()));
  return address.port;
}

async function poll<T>(read: () => Promise<T>, accept: (value: T) => boolean): Promise<T> {
  for (let i = 0; i < 60; i++) {
    const value = await read();
    if (accept(value)) return value;
    await new Promise((done) => setTimeout(done, 150));
  }
  throw new Error('Fixture exceeded 60 bounded polls');
}

test.beforeAll(async ({ request }) => {
  const port = await unusedPort();
  backendURL = `http://127.0.0.1:${port}`;
  const python = process.env.JOURNEY_PYTHON ?? 'python3';
  backend = spawn(python, ['-m', 'tests.fixtures.journey_server', '--port', String(port)], {
    cwd: resolve(process.cwd(), '..'),
    stdio: 'ignore'
  });
  await poll(async () => {
    if (backend.exitCode !== null) throw new Error(`Fixture exited ${backend.exitCode}`);
    try { return (await request.get(`${backendURL}/health`)).ok(); } catch { return false; }
  }, Boolean);
});

test.afterAll(async () => {
  if (!backend || backend.exitCode !== null) return;
  await new Promise<void>((done) => {
    const force = setTimeout(() => backend.kill('SIGKILL'), 3_000);
    const limit = setTimeout(done, 5_000);
    backend.once('exit', () => {
      clearTimeout(force);
      clearTimeout(limit);
      done();
    });
    backend.kill('SIGTERM');
  });
});

test('reads a persisted edition and sees podcast failure recover in the live app', async ({ page, request }, testInfo) => {
  const registration = await request.post(`${backendURL}/api/auth/register`, {
    data: { username: 'journey-browser', password: 'journey-password-123' }
  });
  expect(registration.ok()).toBeTruthy();
  const token = (await registration.json()).access_token as string;
  const headers = { Authorization: `Bearer ${token}` };

  // Transparent same-origin proxy: every API response comes from the live FastAPI process.
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const response = await route.fetch({ url: `${backendURL}${url.pathname}${url.search}` });
    await route.fulfill({ response });
  });
    await page.goto('/digests');
    await page.getByLabel('Username').fill('journey-browser');
    await page.getByLabel('Password').fill('journey-password-123');
    await page.getByRole('button', { name: 'Sign In' }).click();
    await expect(page.getByRole('heading', { name: 'Digests' })).toBeVisible();
    await page.getByRole('button', { name: 'Generate Digest' }).first().click();

    const digest = await poll(async () => {
      const response = await request.get(`${backendURL}/api/digests`, { headers });
      return (await response.json())[0] as { id: string; status: string; filename: string } | undefined;
    }, (item) => item?.status === 'completed');
    expect(digest?.status).toBe('completed');
    await page.reload();
    await expect(page.getByRole('button', { name: 'Read' }).first()).toBeVisible();
    await page.getByRole('button', { name: 'Read' }).first().click();
    await expect(page.getByText('Synthetic Observatory').first()).toBeVisible();
    await expect(page.getByText(/synthetic observatory records a clear sky/i).first()).toBeVisible();
    await expect(page.getByText('Reader mode unavailable')).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath('journey-reader.png'), fullPage: true });

    const preferences = await request.put(`${backendURL}/api/podcast/preferences`, {
      headers, data: { podcast_feed_enabled: true }
    });
    expect(preferences.ok()).toBeTruthy();
    const started = await request.post(`${backendURL}/api/digests/${digest!.id}/podcast`, { headers });
    expect(started.ok()).toBeTruthy();
    const episodeId = (await started.json()).episode_id as string;
    const failed = await poll(async () => {
      const response = await request.get(`${backendURL}/api/digests/${digest!.id}/podcast`, { headers });
      return (await response.json()).episode as { status: string; error_message: string };
    }, (item) => item.status === 'failed');
    expect(failed.error_message).toContain('Synthetic provider interruption');
    await page.goto('/episodes');
    await expect(page.getByText('Synthetic provider interruption').first()).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath('journey-failure.png'), fullPage: true });
    await page.getByRole('button', { name: 'Retry' }).first().click();
    const ready = await poll(async () => {
      const response = await request.get(`${backendURL}/api/digests/${digest!.id}/podcast`, { headers });
      return (await response.json()).episode as { status: string };
    }, (item) => item.status === 'ready');
    expect(ready.status).toBe('ready');
    await page.reload();
    await expect(page.getByRole('link', { name: 'Listen' }).first()).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath('journey-ready.png'), fullPage: true });

    const privateFeed = await request.get(`${backendURL}/api/podcast/feed/info`, { headers });
    const feedURL = (await privateFeed.json()).feed_url as string;
    expect((await request.get(feedURL)).status()).toBe(200);
    expect((await request.get(`${backendURL}/api/podcast/feed.xml?token=wrongtoken`)).status()).toBe(401);
    expect((await request.get(`${backendURL}/api/podcast/episodes/${episodeId}/stream`)).status()).not.toBe(200);
});
