# Project audit: Bengaluru Transit Planner 4.0 (Phase 0)

Audit date: 16 November 2026. Baseline: `main` at commit `1fda4de` (release 3.0.0, plus the Render, APK and icon work).
Version 3.0 is preserved: it stays on `main` and is tagged `v3.0.0`. All 4.0 work happens on the `v4` branch.

**Git state:** 9 commits on `main`, clean working tree, branches `main` and `v4`, tags `v3.0.0` and `app-latest`.
**Documents read:** README, SOURCES, CHANGELOG, `docs/SECURITY_ASVS.md`, `docs/PRIVACY.md`, `docs/DEPLOY.md`,
`docs/API.md`, `docs/architecture.md`, `android/README.md`.

**Phase 0 document set** (all in `docs/4.0/`): this audit, `ARCHITECTURE_4_0.md`, `IMPLEMENTATION_ROADMAP_4_0.md`,
`API_INTEGRATION_REGISTER.md`, `DATA_SOURCE_REGISTER.md`, `SECURITY_PLAN_4_0.md`, `TEST_PLAN_4_0.md`, plus
supporting `FEATURE_MATRIX_4_0.md` (includes the Namma BMTC 2.0 comparison), `DATABASE_DESIGN_4_0.md` and
`DEPLOYMENT_AND_RELEASE_4_0.md`.

## 1. What exists today

### Backend (Python 3.11+, FastAPI, SQLAlchemy 2, Alembic)

| Module | Lines | Role |
|---|---:|---|
| `backend/app/api.py` | 764 | 38 API operations under `/api` (see below) |
| `backend/app/gtfs/importer.py` | 965 | GTFS ZIP import with checks before any row is stored; `COMPLETED`/`REJECTED` records |
| `backend/app/services/planner.py` | 862 | RAPTOR journey planner, up to 2 changes, walking transfers, works across several feeds of one classification |
| `backend/app/services/schedule.py` | 754 | Route timetables, stop departures, search, nearby stops |
| `backend/app/services/exports.py` | 326 | CSV and PDF exports |
| `backend/app/services/maintenance.py` | 214 | Backups, database checks, statistics |
| `backend/app/services/scenarios.py` | 195 | Future "what if" scenarios with labelled estimates |
| `backend/app/models.py` | 341 | 18 tables |
| `backend/app/security.py` | 89 | Admin key check, device key hashing, rate limiting, safe filenames |
| `backend/app/clock.py` | 100 | Service time zone and GTFS service days |

**API operations (38):**
- Public: `health`, `clock`, `meta`, `years/{year}/status`, `years/compare`, `routes`, `routes/{id}`, `routes/{id}/timetable` (+`.csv`), `stops`, `stops/nearby`, `stops/{id}/departures`, `journey`, `plan`, `data-sources`.
- Per-device (`X-Client-Key`): scenarios (CRUD, compare, CSV/PDF), saved routes, preferences.
- Admin (`ADMIN_API_KEY`): data sources (create, verify/revoke), imports (upload, list, delete), stats, backup, audit log.

**Database (18 tables):** `data_sources`, `verification_records`, `gtfs_imports`, `agencies`, `routes`, `stops`,
`service_calendars`, `service_exceptions`, `trips`, `stop_times`, `shape_points`, `fare_attributes`, `fare_rules`,
`scenarios`, `scenario_stops`, `saved_routes`, `user_preferences`, `audit_logs`. Migrations: `0001` baseline, `0002` fares.

### Web app / PWA (`dashboard/`, no build step)
- Plain HTML/CSS/JS: `app.js` 2,331 lines, `i18n.js` (English, Kannada, Telugu, Hindi, 344 keys each), Leaflet 1.9.4 vendored.
- 7 views: Routes and timetables, Stops, Plan a journey, Future scenarios, Compare, Data sources, Administration.
- Service worker: network-first app shell; keeps up to 120 public timetable answers for offline reading; never caches
  time-dependent, personal, planning or admin answers.
- Installable (manifest + icons, maskable icon, new BMTC Planner branding).

### Security controls in place
Constant-time admin key check; device keys stored only as SHA-256; per-IP rate limit (120/min); CSP allowing only
same-origin scripts; `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`; upload size, ZIP member and
compression-ratio limits; audit log for admin actions; OWASP ASVS 5.0 self-mapping in `docs/SECURITY_ASVS.md`.

### Deployment
- Docker image (`python:3.13-slim`, non-root user). `scripts/container_start.sh` seeds the demo feed on Render and
  trusts Render's proxy for client IPs.
- Docker Compose + Caddy kit for HTTPS self-hosting (written, not run).
- Live demo on Render free tier: `https://bmtc-future-transit-planner-3-0.onrender.com` (manual deploys).

### Android
- `android/flutter_app`: a Flutter WebView wrapper (one `main.dart`). It loads the live URL and blocks other hosts.
- GitHub Actions builds a release APK (debug-signed) with adaptive icon and launch screen, published on release `app-latest`.
- Not done: back-button handling, location permission, offline screen, deep links, release signing.

### Quality
- 366 automated tests on Linux (361 passed + 5 font-dependent skips on Windows), 121 browser checks, mutation checks,
  restore drill, ruff, bandit. CI runs lint, migrations and tests on Python 3.12 and 3.13.

## 2. Strengths to build on
1. **The planner is already multi-feed.** RAPTOR combines several feeds of one classification with walking transfers.
   A Metro GTFS feed imported next to a bus feed gives bus + Metro journeys with little new routing code.
2. **Data honesty is designed in.** The three classifications (official verified / unverified feed / estimated) and the
   source labels are exactly what 4.0's "never fake official data" rule needs.
3. **No-build frontend.** One codebase serves the web, the PWA and the Android wrapper, which is what a ₹0 budget needs.
4. **Strong test culture**, which lets 4.0 change things safely.

## 3. Gaps against the 4.0 brief (summary; details in `FEATURE_MATRIX_4_0.md`)

| Area | Gap |
|---|---|
| Data | No official BMTC or Metro data loaded; only the synthetic demo feed |
| Mobile UI | Desktop-style sidebar layout; no home dashboard, tiles, bottom navigation or splash animation |
| Metro | No Metro module, no station directory, no interchange data |
| Live tracking | No GTFS-Realtime ingestion; no live data source is available |
| Accounts | Only anonymous device keys; no registration, login, profile, deletion or export |
| Favourites | Saved routes only (per device); no saved stops, journeys or recent searches |
| Facilities, airport, SOS, help | Not present |
| Tickets, passes, payments, NCMC | Not present, and **cannot be activated** without authorised providers |
| AI assistant | Not present |
| Admin | Single shared admin key; no roles, no provider health or feature-flag screens |
| Android | WebView wrapper without back navigation, permissions, offline screen or release signing |

## 4. Risks and blockers found

| # | Risk | Impact | Proposed handling |
|---|---|---|---|
| R1 | **Name and look-alike risk.** "BMTC" in the name, and a home screen modelled on Namma BMTC, can read as official. App stores remove apps that imply an affiliation they don't have. | High | Decision D-NAME in `ARCHITECTURE_4_0.md`. Keep the "Unofficial" notice everywhere regardless. |
| R2 | **No persistent database on the free host.** Render free disk is wiped on restart, so accounts and favourites would vanish. | High for Phase 5 | Decision D-DB: a free hosted Postgres (for example Neon), set up from your account. |
| R3 | **No official data licence confirmed.** The DULT Transport Data Hub is reported but its terms are unknown. | High | Contact DULT/BMTC; until then use only data whose terms are known, labelled `UNVERIFIED_FEED`. |
| R4 | **Ticketing, payments, NCMC and live GPS need organisations, not code.** ONDC buyer-app registration, payment-gateway KYC and agency data agreements all need a registered entity. | Blocks Phases 7–8 activation | Build adapters and UI states; keep features `DISABLED` with the reason shown. |
| R5 | **Map tiles.** The default OpenStreetMap tile servers have a usage policy that does not allow heavy app traffic. | Medium | Configurable tile provider; attribution; switch to a free-tier key or self-hosted tiles as usage grows. |
| R6 | **No licence file.** Nobody may legally reuse the code; F-Droid will not list it. | Medium | Choose a licence (for example MIT). |
| R7 | **Single shared admin key.** No per-person accountability. | Medium | Phase 10 role-based admin accounts. |
| R8 | **APK is debug-signed.** Phones show risk warnings; updates break if the key changes. | Medium | Release keystore stored as GitHub secrets (your action). |
| R9 | **Translations unreviewed.** | Medium | Native-speaker review checklist (Phase 1). |
| R10 | **Free-tier limits.** Render free: 512 MB RAM, sleeps after ~15 min idle. | Medium | Keep the backend light (no OpenTripPlanner/JVM); document limits. |

## 5. Test baseline before 4.0
- `python -m ruff check .` — passes.
- `python -m pytest` — 361 passed, 5 skipped (Windows, DejaVu Sans font missing); 366 passed on Linux CI.
- CI on `main` — green; Android APK build — green.
