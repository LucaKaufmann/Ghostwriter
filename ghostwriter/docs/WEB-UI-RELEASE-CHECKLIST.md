# Ghostwriter Web UI Overhaul - Release Checklist

Last updated: 2026-02-13
Owner: Frontend
Scope: FE-001 through FE-100

## Release Gate
- [x] `npm run check` passes
- [x] `npm run build` passes
- [x] `npm run test:e2e` passes
- [x] Light and dark theme snapshots captured for Dashboard, Feeds, Digests, Settings
- [x] Keyboard and accessibility pass completed for updated interactions (settings integrations row, nav actions, reader controls)

## Ticket Closure
| Ticket | Status | Notes |
|---|---|---|
| FE-001 | Closed | Theme runtime + persistence + no-flash bootstrap |
| FE-002 | Closed | Semantic status tokens applied |
| FE-003 | Closed | Shared date/digest helpers extracted |
| FE-004 | Closed | Auth logging cleanup and clearer auth errors |
| FE-005 | Closed | Oversized routes split into feature components |
| FE-006 | Closed | Frontend contributor docs rewritten |
| FE-010 | Closed | Settings information architecture split into tabs |
| FE-020 | Closed | Dashboard shifted to action-first workflow |
| FE-030 | Closed | Feeds filters, validation, and bulk actions shipped |
| FE-040 | Closed | Digests filters/sort/load-more/action discoverability shipped |
| FE-045 | Closed | Reader controls + persisted preferences + keyboard shortcuts shipped |
| FE-050 | Closed | Newsletters state messaging and reconnect flow clarified |
| FE-060 | Closed | App shell context cues + global quick action shipped |
| FE-070 | Closed | A11y suppression removals and keyboard-safe interactions |
| FE-080 | Closed | Playwright smoke + light/dark visual checks |
| FE-090 | Closed | Lazy route loading + query refetch tuning + reader module caching |
| FE-100 | Closed | Release checklist + rollout validation documented |

## Performance Notes (FE-090)
- Heavy feature route modules now lazy-load from lightweight route wrappers.
- Reader parsing dependencies are cached after first load.
- Dashboard and digests queries now avoid unnecessary refetch on window focus where not needed.
- Build output now splits feature chunks (`FeedsPage`, `DigestsPage`, `ReaderPage`, `SettingsPage`) from thin route entry points.

## QA Matrix
| Surface | Desktop Light | Desktop Dark | Mobile Light | Mobile Dark |
|---|---|---|---|---|
| Login/Auth gate | ✅ | ✅ | ✅ | ✅ |
| Dashboard | ✅ | ✅ | ✅ | ✅ |
| Feeds | ✅ | ✅ | ✅ | ✅ |
| Digests list | ✅ | ✅ | ✅ | ✅ |
| Reader | ✅ | ✅ | ✅ | ✅ |
| Settings | ✅ | ✅ | ✅ | ✅ |
| Newsletters | ✅ | ✅ | ✅ | ✅ |

## Rollout Plan
1. Deploy to staging and verify e2e suite plus manual smoke checks.
2. Deploy to production with normal release pipeline.
3. Watch logs and user-facing errors for 30 minutes post-deploy.
4. Confirm no new auth, digest, or route-load regressions.

## Post-Release Monitoring Focus
- Digests page query load and filter interactions
- Reader parsing fallback behavior
- Theme persistence and no-flash load behavior
- Navigation and auth gate reliability

## Fast-Follow Queue
- None required at release sign-off.
