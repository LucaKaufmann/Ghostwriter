# Ghostwriter Web UI - Implementation Plan

> **Branch:** `feature/ghostwriter-web-ui`  
> **Goal:** Build a polished, user-friendly web frontend for Ghostwriter configuration and monitoring.  
> **Constraint:** Use the existing API where possible. Minor backend additions allowed when needed.

---

## Phase 1: Foundation ✅
*Estimated: 1-2 sessions*

### 1.1 Project Setup
- [x] Initialize SvelteKit project in `ghostwriter/frontend/`
- [x] Configure Tailwind CSS
- [x] Add shadcn-svelte UI components
- [x] Set up Tanstack Query for API calls
- [x] Create API client with typed endpoints
- [x] Configure proxy for local development (`/api` → FastAPI)

### 1.2 Layout & Navigation
- [x] Create app shell (sidebar + main content area)
- [x] Navigation: Dashboard, Feeds, Digests, Newsletters, Settings
- [x] Mobile-responsive layout
- [x] Dark mode support (via shadcn theme system)

### 1.3 Authentication
- [x] API token input/storage (localStorage)
- [x] Auth context provider (Svelte store)
- [x] Protected route wrapper
- [x] Logout / clear token
- [x] **User accounts with JWT authentication**
- [x] First-run registration flow (admin account setup)
- [x] Username/password login
- [x] API token management (create/revoke)
- [x] Legacy API_KEY backward compatibility

---

## Phase 2: Core Screens ✅
*Estimated: 2-3 sessions*

### 2.1 Dashboard (`/`)
- [x] Server status card (health endpoint)
- [x] Active job indicator (if digest running)
- [x] Stats: feed count, last digest date, next scheduled run
- [x] Quick actions: trigger digest, view latest
- [x] Recent digests list (last 5)

### 2.2 Feeds (`/feeds`)
- [x] Feed list table with columns: Title, URL, Mode, Max Articles, Status
- [x] Search/filter feeds
- [x] Add feed modal
  - [x] URL input with validation
  - [x] Title (optional, defaults to URL)
  - [x] Mode selector (raw/summarize)
  - [x] Max articles input
- [x] Edit feed modal (title, mode, max articles, active toggle) — *implemented with new PUT /feeds/{id} endpoint*
- [x] Delete feed with confirmation
- [ ] Bulk actions: delete selected, toggle mode — *deferred for simplicity*

### 2.3 Digests (`/digests`)
- [x] Digest history table: Date, Period, Status, Article Count, Actions
- [x] Download button (direct EPUB link)
- [x] View articles modal (expandable list)
- [x] Delete digest with confirmation
- [x] Manual trigger button with loading state
- [x] Job progress indicator when running

---

## Phase 3: Integrations & Settings ✅
*Estimated: 1-2 sessions*

### 3.1 Newsletters (`/newsletters`)
- [x] Gmail connection status card
- [x] Connect Gmail button → OAuth flow
- [x] Re-authorize option
- [x] Label display (from server config)
- [x] Instructions/help text for setup

### 3.2 Settings (`/settings`)
- [x] **AI Configuration** (read-only display)
  - [x] Provider display
  - [x] Model display
  - *Note: These are server-side env vars, not changeable via UI*
- [x] **Schedule Configuration**
  - [x] Morning/Noon/Evening time pickers
  - [x] Enable/disable toggles per period
  - [x] Timezone display
- [x] **Retention Settings** (read-only display)
  - [x] Digest retention days
  - [x] Max articles per digest
- [x] **API Token**
  - [x] Display current token (masked)
  - [x] Copy to clipboard
  - [x] Show/hide toggle
  - [x] Note about env var configuration

---

## Phase 4: Polish & Integration ✅
*Estimated: 1-2 sessions*

### 4.1 UX Polish
- [x] Loading skeletons for all data fetches
- [x] Error states with retry buttons (via TanStack Query)
- [x] Toast notifications for actions
- [x] Confirm dialogs for destructive actions
- [x] Empty states with helpful prompts

### 4.2 Docker Integration
- [x] Build step in Dockerfile (multi-stage with Node.js)
- [x] FastAPI serves static files from `/frontend/build`
- [x] Fallback route for SPA routing
- [x] Environment-based API URL configuration (via Vite proxy in dev)

### 4.3 Documentation
- [x] Update README with web UI section
- [ ] Screenshots in docs — *deferred: requires running instance*
- [ ] First-time setup guide — *covered in README*

---

## Phase 5: Future Enhancements (Optional)
*Post-launch improvements*

- [ ] OPML import/export for feeds
- [ ] Feed preview (fetch and show recent items)
- [ ] Digest preview in browser (EPUB → HTML)
- [ ] Wallabag integration settings
- [ ] Push notification configuration
- [x] ~~Multi-user support~~ → User accounts with JWT auth implemented
- [ ] PWA support (installable, offline basics)

---

## Tech Stack Summary

| Component | Choice |
|-----------|--------|
| Framework | SvelteKit (static adapter) |
| Styling | Tailwind CSS |
| Components | shadcn-svelte |
| Data Fetching | Tanstack Query (@tanstack/svelte-query) |
| Icons | Lucide |
| Build | Vite |
| Deployment | Bundled with FastAPI Docker image |

---

## API Endpoints Used

| Endpoint | Screen |
|----------|--------|
| `GET /health` | Dashboard |
| `GET /config` | Dashboard, Settings |
| `PUT /config` | Settings |
| `GET /feeds` | Feeds |
| `POST /feeds` | Feeds (add) |
| `PUT /feeds/{id}` | Feeds (edit) |
| `DELETE /feeds/{id}` | Feeds (delete) |
| `POST /feeds/sync` | Feeds (bulk) |
| `GET /digests` | Digests |
| `GET /digests/latest` | Dashboard |
| `GET /digests/{id}/status` | Digests (progress) |
| `GET /digests/{id}/articles` | Digests (detail) |
| `POST /digests/trigger` | Dashboard, Digests |
| `DELETE /digests/{filename}` | Digests |
| `GET /newsletters/status` | Newsletters |
| `GET /newsletters/oauth/start` | Newsletters |
| `GET /schedules` | Settings |
| `GET /auth/status` | Login |
| `POST /auth/register` | Login (first run) |
| `POST /auth/login` | Login |
| `GET /auth/me` | Settings |
| `PUT /auth/me` | Settings |
| `GET /auth/tokens` | Settings |
| `POST /auth/tokens` | Settings |
| `DELETE /auth/tokens/{id}` | Settings |

---

## Notes

- **Minimal backend changes** — added PUT /feeds/{id} for edit functionality
- **Mobile-first** — many users may check from phone
- **Offline resilience** — graceful handling of API unavailability
- **Security** — token stored in localStorage, no sensitive data cached

---

*Created: 2026-01-28*  
*Last updated: 2026-01-28*
