# Ghostwriter frontend

This SvelteKit frontend uses Node 24 and the checked-in npm lockfile.

```sh
npm ci
npm run check
npm run build
npm run dev
```

## Browser checks

The Playwright tests use synthetic, fixture-backed API responses. They check authentication, current navigation, the legacy `/feeds` redirect, and core page rendering without a backend or external provider. Unknown API endpoints and external requests fail the tests. These checks do not prove backend integration or content generation.

```sh
npm ci
npx playwright install chromium
npm run test:e2e -- --project=behavior
```

On Linux, install Chromium system dependencies and run the reviewed visual project as well:

```sh
npx playwright install --with-deps chromium
npm run test:e2e -- --project=visual
```

`npm run test:e2e` runs both projects. The visual project compares platform-specific screenshots in `tests/e2e/navigation-theme.spec.ts-snapshots/`; behavior tests are portable across host platforms. When a deliberate UI change alters a screenshot, generate candidate snapshots on the target platform with `npx playwright test --project=visual --update-snapshots`, inspect the rendered images, then commit the reviewed differences. Do not update snapshots solely to make a failure pass. CI uploads Playwright traces, screenshots, and the HTML report when a browser check fails.
