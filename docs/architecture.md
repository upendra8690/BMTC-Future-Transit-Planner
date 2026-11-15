# Architecture

The planner is one Python process. It serves a JSON API under `/api/` and the web dashboard at `/`, and keeps its data in
one SQLite file. The main design rule is that verified timetables, unverified feeds and future estimates are stored and
shown apart, and no code path moves data from one class to another without an explicit, recorded decision.

## Components

```
Browser: dashboard (HTML, CSS, vanilla JavaScript, Leaflet 1.9.4, service worker)
    |  HTTP: /api/... returns JSON, CSV or PDF; / returns the dashboard files
    v
FastAPI application (backend/app/main.py)
    middleware, in order:
      1. rate limit per client IP, for /api/ paths only (429 with Retry-After: 60)
      2. security headers on every response; Content-Security-Policy on non-API responses
    router (backend/app/api.py): 35 operations under /api
    |
    +-- services: schedule, scenarios, verification, audit, exports, maintenance
    +-- gtfs: importer (validation and import), synthetic (demo feed generator)
    +-- security: administrator key, device key, safe file names, rate limiter
    |
SQLAlchemy 2.x ORM (16 tables) --> SQLite file data/planner.db
Alembic migrations (migrations/) are applied at start-up
```

## Modules

| Path | Responsibility |
|---|---|
| `backend/app/main.py` | Application factory `create_app(settings)`, middleware, security headers, dashboard mount. |
| `backend/app/api.py` | The 35 API operations: timetables, stops, journeys, scenarios, saved routes, preferences and administration. |
| `backend/app/config.py` | Settings from environment variables and `.env`. Environment variables already set take precedence. |
| `backend/app/database.py` | SQLAlchemy engine and sessions, SQLite connection settings. |
| `backend/app/models.py` | The 16 tables, classification constants, source kinds and weekday codes. |
| `backend/app/schemas.py` | Request validation (Pydantic). Planning years are 2027 to 2030. |
| `backend/app/security.py` | Administrator key check, device key format and hashing, safe file names, sliding-window rate limiter. |
| `backend/app/schema_migrations.py` | Applies migrations at start-up, and marks databases built before migrations existed. |
| `backend/app/gtfs/importer.py` | Opens and checks a GTFS ZIP, validates the tables, and stores them in chunks of 5,000 rows. |
| `backend/app/gtfs/synthetic.py` | Writes the invented demonstration feed. Labelled `SYNTHETIC_DEMO`. |
| `backend/app/services/schedule.py` | Year coverage, operating days, route and stop search, timetables, direct journeys, nearby stops. |
| `backend/app/services/scenarios.py` | Owner-scoped scenario records, the estimate calculation, comparison. |
| `backend/app/services/verification.py` | Verifies or revokes a source, and reclassifies its imports. |
| `backend/app/services/audit.py` | Writes audit entries. |
| `backend/app/services/exports.py` | CSV and PDF output. The PDFs are built with ReportLab. |
| `backend/app/services/maintenance.py` | Online SQLite backup, backup verification and the database check. |
| `dashboard/` | Single-page dashboard: `index.html`, `app.js`, `styles.css`, service worker `sw.js`, manifest, icons, vendored Leaflet. |
| `scripts/` | Command-line tools (import, migrate, check, backup, demo feed) and the Windows `.bat` launchers. |
| `migrations/` | Alembic environment and the baseline migration. |
| `android/flutter_app/` | A Flutter starter that opens the dashboard in a WebView. It is not built. |
| `tests/` | Automated tests. `tests/browser/` holds the browser checks, and `tests/mutation/` holds the mutation check. |

## Data flow

### Importing a timetable feed

1. The ZIP arrives from the admin upload endpoint or from `scripts/import_gtfs.py`. Its size is limited by `MAX_UPLOAD_MB`.
2. Before anything is read, the archive is checked for path traversal, absolute paths, drive letters, encrypted members,
   member count, total uncompressed size and suspicious compression ratios.
3. The required files (`agency.txt`, `routes.txt`, `stops.txt`, `trips.txt`, `stop_times.txt`) and the optional files
   (`calendar.txt`, `calendar_dates.txt`, `shapes.txt`) are read and validated. Checks cover identifiers, duplicates,
   references, dates, times, coordinates and UTF-8 text. A feed whose service dates span more than three years gets a
   warning, not a rejection.
4. The SHA-256 of the file is compared with completed imports. An identical file gets a warning.
5. If validation fails, the attempt is stored as `REJECTED` with its errors. No timetable rows are stored.
6. If it passes, the rows are inserted in chunks of 5,000 and the import is stored as `COMPLETED`. Dates that overlap an
   existing import of the same classification produce a warning, and each import is searched separately.

### Classification

Every import gets a classification when it is stored:

| Classification | Meaning | How it is assigned |
|---|---|---|
| `OFFICIAL_VERIFIED` | Confirmed through an authoritative source and verified by an administrator. | Only a source of kind `OFFICIAL` that has a verification record. |
| `UNVERIFIED_FEED` | Any other feed: community, synthetic, unknown, or an official source not yet verified. | Everything else. |
| `ESTIMATED_SCENARIO` | A proposal or simulation. | Scenario records only. Never stored as timetable rows. |

These rules live in `classification_for_source` (`importer.py`), `set_verification` (`verification.py`) and
`eligible_import_ids` (`schedule.py`). Verifying or revoking a source calls `reclassify_source_imports`, which updates
every import of that source. The change is recorded in `verification_records` and `audit_logs`.

### Answering a timetable question

The API takes a classification. `eligible_import_ids` returns only the completed, active imports of that classification,
and, for a year, only those whose service dates overlap it. `year_coverage` works out whether that year is fully,
partly or not covered, and produces the message shown above the results. When the official classification has no
coverage for a year, the message is `No officially verified timetable is available for this future year.` and no
official routes are listed.

### Scenarios

A scenario belongs to one device, identified by a hash of its `X-Client-Key`. It has an origin, a destination, optional
intermediate stops, a route number, a year (2027 to 2030) and a frequency. The estimate is calculated from those numbers
and the configured assumptions:

- distance: the straight-line length of each leg (haversine), summed, multiplied by the road detour factor (default 1.3)
- journey time: distance divided by the average bus speed (default 15 km/h), in minutes, plus the dwell time (default
  0.5 minutes) for each intermediate stop
- departures per day: (last departure minus first departure) divided by the frequency, plus one; departures per week
  is that figure multiplied by the number of operating days

All of these defaults are placeholders to be calibrated. The output says so. A warning is added when the scenario's route
number matches an official route in the same year. Scenarios are compared side by side and can be exported as CSV or PDF.

### Administration

An administrator signs in with the administrator key. The dashboard can upload a feed, create a data source, verify or
revoke an `OFFICIAL` source, delete an import together with its timetable rows, create a backup and read the audit log.
The command-line tools can import a feed, create a source, verify or revoke a source, and back up the database. Changes to
data, verification decisions and administrative actions write audit entries. The backup script works on the database file
and writes none.

## Security model

| Layer | What it does |
|---|---|
| Rate limiter | Counts requests per client IP and returns 429 after `RATE_LIMIT_PER_MINUTE` (default 120) on `/api/` paths. |
| Security headers | `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options: DENY`, and `Permissions-Policy`, which allows geolocation only for the page itself and turns off camera, microphone, payment and USB. |
| Content Security Policy | On dashboard pages: scripts only from the same origin (no inline scripts), no framing, a form and base URI limited to the same origin. Map tiles come from OpenStreetMap. |
| Administrator key | Sent in the `X-Admin-Key` header and compared in constant time. If `ADMIN_API_KEY` is empty, every administrative route returns 503. Wrong or missing keys return 401. |
| Device key | Sent in `X-Client-Key`. It must be 16 to 128 characters of letters, digits, `_` or `-`. Only its SHA-256 hash is stored. |
| Input checks | Pydantic schemas validate request bodies. GTFS checks reject hostile archives. Uploaded file names are reduced to safe characters. Search text escapes `%`, `_` and `\` so they match literally. |
| Queries | Application queries go through the ORM with bound parameters. Raw SQL is limited to constant statements and one counting query that inserts table names taken from the model metadata. |
| Audit | Data-changing and administrative actions write `audit_logs` entries with the actor, action, entity and, for some actions, the client IP. |
| Storage | Credentials are sent in headers, not cookies, so ordinary cross-site form posts cannot use them. |

### Limits of the security model

- There are no user accounts, and no TLS. Served over plain HTTP, the administrator key and device keys travel unencrypted.
- The administrator key is not checked for length, and there is no lockout after failed attempts. Use a long random key.
- A device key is a bearer credential. Anyone who has it, or the browser profile that holds it, can use that device's
  scenarios and saved routes.
- The device key is kept in the browser's `localStorage`, and the administrator key only in `sessionStorage` for the
  tab's lifetime.
- The rate limiter lives in one process's memory. Behind a reverse proxy, every client appears to come from the proxy's
  address, so the limit and the audit IP addresses refer to the proxy. The planner does not read `X-Forwarded-For`.
- Audit entries are never removed by the planner.

## Dashboard

The dashboard is a single page with hash routes: `#/routes`, `#/stops`, `#/journey`, `#/scenarios`, `#/compare`,
`#/sources` and `#/admin`. It has no build step and uses no framework.

- It stores the device key in `localStorage`, the chosen year and classification there too, and the administrator key in
  `sessionStorage`.
- The service worker caches only the shell files (the page, scripts, styles, manifest, icons and Leaflet). Requests under
  `/api/` are always sent to the network and never cached.
- Browsers register service workers, and grant geolocation, only in secure contexts (HTTPS or `localhost`). The dashboard
  checks for these features and degrades without errors.

## Tests

| Layer | Where | What it covers |
|---|---|---|
| Unit and service | `tests/test_schedule.py`, `test_scenarios.py`, `test_gtfs_importer.py`, `test_security.py` | Queries, estimate arithmetic, GTFS rules, key handling, rate limiter. |
| API | `tests/test_api.py`, `test_hardening.py` | The API routes, administrator gating, classification rules, security headers and the 429 response. |
| Search | `tests/test_search.py` | Literal matching of `%`, `_` and `\`, blank input. |
| Command-line | `tests/test_cli.py` | Import, verification and exit codes. |
| Migrations | `tests/test_migrations.py` | New database at head matches the models; legacy databases keep their rows; upgrade and downgrade. |
| Maintenance | `tests/test_maintenance.py` | Database check, verified backup, failed backups are removed, script exit codes. |
| Browser | `tests/browser/` | 36 checks in headless Chrome through Playwright, desktop and a Pixel 7 device profile. |
| Mutation | `tests/mutation/mutation_check.py` | Breaks five safety rules one at a time in temporary copies. Each broken copy must make a test fail. Run by hand, not by `pytest`. |

Every test that touches a database uses its own temporary database. The results are in `docs/TEST_RESULTS.md`.

## Known structural limits

- One process and one SQLite file are assumed. Several worker processes would need a shared rate-limit store, and
  SQLite under heavy concurrent writes is not load-tested.
- PostgreSQL is supported through SQLAlchemy in principle but is not tested.
- The planner has no background jobs. Nothing is pruned, and nothing refreshes an import automatically.
- Live bus positions are not shown, because no authorised live feed is connected.
