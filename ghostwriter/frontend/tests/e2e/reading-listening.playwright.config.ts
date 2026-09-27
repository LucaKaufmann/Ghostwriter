import { defineConfig } from '@playwright/test';

// Dedicated browser fixture port; override when parallel work uses this checkout.
declare const process: { env: Record<string, string | undefined> };
const port = Number(process.env.JOURNEY_FRONTEND_PORT ?? '4187');

export default defineConfig({
  testDir: '.',
  testMatch: 'reading-listening.spec.ts',
  timeout: 60_000,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: 'chromium',
    trace: 'on',
    viewport: { width: 1440, height: 900 },
    locale: 'en-US',
    timezoneId: 'UTC'
  },
  webServer: {
    command: `npm run build && npm run preview -- --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    timeout: 240_000
  }
});
