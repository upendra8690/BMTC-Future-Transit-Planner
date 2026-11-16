# Test plan for 4.0

## Baseline (before any 4.0 code), 16 November 2026
| Check | Command | Result |
|---|---|---|
| Lint | `python -m ruff check .` | All checks passed |
| Tests (Windows, Python 3.12) | `python -m pytest` | 361 passed, 5 skipped (DejaVu Sans font not installed) |
| Tests (CI, Linux, Python 3.12 and 3.13) | GitHub Actions `CI` | Passed |
| Android APK build | GitHub Actions `Android APK` | Passed (debug-signed) |
| Browser checks (121) | `python tests/browser/run_browser_checks.py` | Last run in the 3.0 build on Linux; **not re-run** in this audit |

Rule: no test is reported as passing unless it ran in that phase, and no test is weakened to make a build pass.

## Test layers

| Layer | Tooling | Runs in |
|---|---|---|
| Unit and service tests | pytest | CI on every push |
| API contract tests | pytest + FastAPI TestClient; OpenAPI snapshot | CI |
| Migration tests | Alembic upgrade from empty and from 3.0 data, on SQLite **and Postgres** (CI service container from Phase 5) | CI |
| Journey planner tests | Fixed GTFS fixtures, including a synthetic Metro line; mutation checks | CI (mutation weekly/manual) |
| Authentication / authorisation | pytest: sessions, CSRF, lockout, cross-user access attempts | CI |
| Security tests | pytest checks for headers, CORS, upload limits, SSRF guards; `pip-audit`; bandit | CI |
| Browser and accessibility | Playwright + axe-core (WCAG 2.1 AA) on the redesigned screens; dark mode; four languages | CI (headless Chromium) |
| Offline / PWA | Playwright with network offline; service worker cache rules | CI |
| Mobile layout | Playwright device profiles (small Android, large Android, iPhone, tablet) | CI |
| Android | APK build; emulator smoke test (app opens, back button, offline screen) | CI (Phase 13) |
| Real device | Owner's checklist (install, icon, location prompt, back, offline) | Manual, recorded with date and device |
| Load | Locust or a small async script against a local server: planner and search endpoints | Manual before release |
| Deployment smoke | `/api/health`, `/api/meta`, one search, one plan against the deployed URL | After each deploy |

## Required negative cases (each must have an automated test)

| Case | Expected behaviour |
|---|---|
| Payment fails or webhook says failed | Order stays unpaid; no ticket created |
| Duplicate payment webhook | Processed once (idempotent) |
| Webhook with bad signature | Rejected and logged as a security event |
| Live feed unavailable / stale | No positions shown; "live tracking unavailable" or "stale since …" |
| No route found / no timetable | Clear empty state, no invented options |
| Feed expired | Labelled expired; not used for "now" |
| User A requests user B's favourites | 404 (no data, no enumeration) |
| Expired or stolen session | 401; session cannot be reused after logout |
| Login with unknown email vs wrong password | Same message and similar timing (no account enumeration) |
| Password reset token reused or expired | Rejected |
| Invalid GTFS upload | Rejected safely, nothing stored |
| Location permission denied | Manual search offered |
| Offline device | Saved data shown with "saved copy" label; actions needing network disabled |
| Database restart (Postgres) | Accounts and favourites still present |
| Metro provider unavailable | Metro info still shown from GTFS; ticketing shows unavailable |
| AI asked for a fare that is not in the data | Says it is unavailable; no number invented |
