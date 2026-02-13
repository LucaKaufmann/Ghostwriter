# Ghostwriter Frontend

SvelteKit frontend for Ghostwriter's web UI. This app is served as static assets by the FastAPI backend in production.

## Requirements
- Node.js 20+
- npm 10+

## Local Development
From this directory:

```bash
npm install
npm run dev
```

The app uses `/api` as the backend base path. In local development, requests are proxied by Vite.

## Scripts
- `npm run dev` - start local dev server
- `npm run check` - run Svelte + TypeScript diagnostics
- `npm run build` - production build (adapter-static)
- `npm run preview` - preview built app

## Architecture
- `src/routes/` - route entry files (thin page containers)
- `src/lib/components/features/` - feature-level page implementations
- `src/lib/components/ui/` - shared shadcn/bits primitives
- `src/lib/components/layout/` - app shell, login, loading, theme switch
- `src/lib/api/` - typed API client
- `src/lib/stores/` - auth and theme state
- `src/lib/utils/` - shared helpers (`date`, `digest`, etc.)

## Theming
Ghostwriter supports `light`, `dark`, and `system` modes.

Implementation details:
- Global tokens live in `src/routes/layout.css`
- Runtime mode behavior uses `mode-watcher`
- Theme preference is managed through `src/lib/stores/theme.ts`
- Theme selector UI is `src/lib/components/layout/ThemeToggle.svelte`

When adding UI:
- Use tokenized classes (`bg-background`, `text-muted-foreground`, semantic status tokens)
- Avoid hardcoded color classes for status states
- Verify contrast in both light and dark modes

## Working Conventions
- Keep route `+page.svelte` files small and orchestration-focused
- Add substantial UI under `src/lib/components/features/<domain>/`
- Reuse existing utility helpers before creating page-local helpers
- Prefer existing UI primitives from `src/lib/components/ui/`

## QA Checklist
Before opening a PR:
1. Run `npm run check`
2. Run `npm run build`
3. Test changed screens in desktop + mobile breakpoints
4. Validate light and dark mode visuals
5. Verify keyboard access and focus behavior for changed interactions

## Build Output
`npm run build` outputs static assets to `build/` (via `@sveltejs/adapter-static`).
The backend serves these files in containerized deployments.
