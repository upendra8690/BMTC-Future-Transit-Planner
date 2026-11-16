# Architecture

The planner is one Python process. It serves a JSON API under `/api/` and the web dashboard at `/`, and keeps its data in one
SQLite file. The main design rule is that verified timetables, unverified feeds and future estimates are stored and shown
apart. Data changes class only when an administrator verifies or revokes a source, and both actions are recorded.

## Components

```
Browser: dashboard (HTML, CSS, vanilla JavaScript, Leaflet 1.9.4, service worker v3, manifest)
    |  HTTP: /api/... returns JSON, CSV or PDF; / and the dashboard files are served from dashboard/
    v
FastAPI application (backend/app/main.py, created by create_app(settings))
    middleware, on every request:
      1. gzip for responses of 1 KB or more
      2. rate limit per client address, for /api/ paths (429 with Retry-After: 60)
      3. security headers on every response, and the dashboard policy on dashboard responses
    router (backend/app/api.py): 38 operations under /api
    |
    +-- services: planner (journeys), schedule (timetables, departures, direct journeys, nearby stops),
    |   scenarios, verification, audit, exports, text (normalising and folding text), maintenance
    +-- gtfs: importer (validation and import, fares included), synthetic (the demonstration feed generator)
    +-- clock: current time, service time zone, service dates around today
    +-- security: administrator key, device key, safe file names, rate limiter
    |
SQLAlchemy 2 ORM (18 tables) --> SQLite file data/planner.db (WAL mode)
Alembic migrations (migrations/: 0001 baseline, 0002 fares) are applied when the application starts
```

## Modules

| Path | Responsibility |
|---|---|
| `backend/app/main.py` | The application factory `create_app(settings)`, middleware, security headers, the dashboard mount, CORS when configured. |
| `backend/app/api.py` | The 38 API operations. |
| `backend/app/config.py` | Settings from environment variables and `.env`. Variables already set in the environment take precedence over `.env`. |
| `backend/app/clock.py` | The current time, the service time zone, the service date, the service day (which starts at noon minus 12 hours, as GTFS defines it), and the candidate service dates: two days back, today and seven days ahead. |
| `backend/app/database.py` | The SQLAlchemy engine and sessions, and the SQLite connection settings. |
| `backend/app/models.py` | The 18 tables, classification constants, source kinds and weekday codes. |
| `backend/app/schemas.py` | Request validation (Pydantic) for scenarios, sources, verification, saved routes and preferences. |
| `backend/app/security.py` | Administrator key check, device key format and hashing, safe file names, the sliding-window rate limiter. |
| `backend/app/schema_migrations.py` | Applies migrations at start-up, and marks databases built before migrations existed as version 0001. |
| `backend/app/gtfs/importer.py` | Opens and checks a GTFS ZIP from memory, validates the tables and the fare files, stores rows in chunks of 5,000, and writes the import record and its audit entry. |
| `backend/app/gtfs/synthetic.py` | Builds the invented demonstration feed. Its agency is named `Demo Transit (SYNTHETIC)`, and it is imported as `SYNTHETIC_DEMO`. `scripts/make_synthetic_gtfs.py` writes it to a file. |
| `backend/app/services/planner.py` | Journey planning across every feed of one classification: the search, the network cache, fares and path reconstruction. |
| `backend/app/services/schedule.py` | Service zone, year coverage, operating days, route and stop search, timetables, departures, direct journeys and nearby stops. |
| `backend/app/services/scenarios.py` | Owner-scoped scenario records, the estimate and the comparison. |
| `backend/app/services/verification.py` | Verifies or revokes a source, requires a non-empty note for verification, and reclassifies the source's imports. |
| `backend/app/services/audit.py` | Writes audit entries. |
| `backend/app/services/exports.py` | CSV and PDF output. PDFs use ReportLab, and the CSV neutralises spreadsheet formulas. |
| `backend/app/services/text.py` | Text normalisation for names and search: Unicode normal forms, spacing and case folding. |
| `backend/app/services/maintenance.py` | Online SQLite backup and its verification, and the read-only database check. |
| `dashboard/` | The single-page dashboard: `index.html`, `app.js`, `i18n.js` (English, Kannada, Telugu and Hindi text), `styles.css`, the service worker `sw.js`, `manifest.webmanifest`, icons, and the vendored Leaflet. |
| `scripts/` | Command-line tools: import, migrate, check, backup, demonstration feed, planner benchmark and restore drill, and the Windows `.bat` launchers. |
| `migrations/` | The Alembic environment, the baseline migration `0001` and the fares migration `0002`. |
| `Dockerfile`, `docker-compose.yml`, `deploy/Caddyfile` | The server kit for Docker and Caddy. Not built in this build; see "Deployment kit". |
| `android/` | A Flutter starter that opens the dashboard in a full-screen WebView. Not built. |
| `tests/` | Automated tests. `tests/browser/` holds the browser checks, and `tests/mutation/` holds the mutation checks. |

## Data flow

### Importing a timetable feed

1. The ZIP arrives from the administration upload or from `scripts/import_gtfs.py`. An upload is limited to `MAX_UPLOAD_MB`
   (100 by default). The ZIP is read from memory and never extracted to disk.
2. Before anything is read, the archive is checked for path traversal, absolute paths, drive letters, encrypted members, the
   number of members (`MAX_ZIP_MEMBERS`, 50 by default), the total uncompressed size (`MAX_UNCOMPRESSED_MB`, 500 by default)
   and suspicious compression ratios (`MAX_COMPRESSION_RATIO`, 100 by default).
3. The required files (`agency.txt`, `routes.txt`, `stops.txt`, `trips.txt`, `stop_times.txt`) and the optional files
   (`calendar.txt`, `calendar_dates.txt`, `shapes.txt`, `fare_attributes.txt`, `fare_rules.txt`) are read and validated.
   Checks cover identifiers, duplicates, references, dates, times, coordinates and text. In `fare_attributes.txt`,
   `payment_method` must be 0 (on board) or 1 (before boarding), and `currency_type` must be a three-letter code.
4. The SHA-256 of the file is compared with completed imports. A file that was imported before gets a warning.
5. If validation fails, the attempt is stored as `REJECTED` with its errors, and the audit entry `gtfs.import_rejected` is
   written. No timetable or fare rows are stored.
6. If the rows cannot be written, the import is stored as `REJECTED` with a generic error, the audit entry `gtfs.import_failed`
   is written, and the exception is logged with the file name.
7. If it passes, the rows are inserted in chunks of 5,000 and the import is stored as `COMPLETED`, with the audit entry
   `gtfs.import`. The import summary gives the number of fare prices stored (`fares`).
8. An import whose dates overlap a completed import of the same classification gets a warning. Both are kept and both are
   searched, so the same route can appear twice in results.

### Classification

Every import gets a classification when it is stored:

| Classification | Meaning | How it is assigned |
|---|---|---|
| `OFFICIAL_VERIFIED` | From an authoritative source, verified by an administrator. | Only a source of kind `OFFICIAL` that is currently verified. |
| `UNVERIFIED_FEED` | Any other feed: community, synthetic, unknown, or an official source not yet verified. | Everything else. |
| `ESTIMATED_SCENARIO` | A proposal or simulation. | Scenario records only. Never stored as timetable rows. |

The rules live in `classification_for_source` (`importer.py`), `set_verification` (`verification.py`) and
`eligible_import_ids` (`schedule.py`). Verifying or revoking a source reclassifies each import of that source. The decision is
written to `verification_records` and `audit_logs`. Verifying needs a non-empty note. The dashboard asks for the evidence (the
publisher's page, the date checked and the licence), but the server checks only that a note was given, not what it says. A
note is kept with each verification record. Revoking needs no note.

### Answering a timetable question

The API takes a classification. `eligible_import_ids` returns the completed, active imports of that classification and, for a
year or a date, only those whose service dates overlap it. `year_coverage` works out whether the year is fully covered, partly
covered or not covered. Its message appears above the results:

- Official data, no coverage in a future year: "No officially verified timetable is available for this future year." A
  current or past year is named instead, so the future wording is never used for it.
- Official data, partial coverage: the covered period is given, and the message says that dates outside it have no verified
  timetable.
- Unverified feed data: "covers all of" the year, "covers only part of" it, or "No unverified feed covers" it.

### Journey planning

`GET /api/plan` finds journeys with up to two changes across every feed of one classification. The search is a round-based
earliest-arrival method in the style of RAPTOR (`backend/app/services/planner.py`):

- **Rounds.** Round `k` finds the earliest arrival at each stop using at most `k` rides. The search runs `max_changes + 1`
  rounds, and `max_changes` is limited to 2.
- **Matching.** The origin and destination texts are matched against stop names, folded for case, and against the feed's stop
  IDs, which must match exactly. A match of more than 200 stops is cut to 200, and `match_note` says so.
- **Walks.** A walk between two stops of the same classification is allowed up to `MAX_TRANSFER_WALK_M` (300 metres by
  default). Walks are not chained, so a walk cannot follow another walk. Walking is at `WALK_SPEED_KMPH` (4.8 km/h by default).
- **Changes.** A change needs at least `MIN_TRANSFER_MINUTES` (3 minutes by default).
- **Lanes.** Trips that share a stop pattern are split into lanes so that no trip in a lane overtakes another. Within a lane,
  an earlier trip is never later at any stop than a later one.
- **Time windows.** In date mode the search covers the two service days before the date and the date itself, so trips that
  run past midnight are found. In now mode it covers the next three hours from the current time, over the service days from
  two days before today to tomorrow.
- **Start times.** In now mode, a journey whose first leg is a walk starts now; otherwise it starts at the first scheduled
  departure. In date mode it starts at the first scheduled departure minus any walk before the first ride.
- **Paths.** Each label keeps its parent label, so the chosen journey is rebuilt and formatted as legs: rides with their route,
  stops and times, and walks.
- **Fares.** A journey with one ride is priced from fare rules that name its route or name no route, and that have no origin,
  destination or contains zone. Fare rules with a zone are stored but not used for a price. A journey with changes is never
  given a total (`CHANGES_NOT_PRICED`).
- **Ordering.** Options are ordered by arrival time, then by number of changes. The labels `EARLIEST_ARRIVAL` and
  `FEWEST_CHANGES` mark the option that is first on each measure.
- **Network cache.** The network for one classification, date range and set of imports is built once and reused. The cache key holds the database address, the classification, the first and last day, the plan settings, and each import's ID and SHA-256, so a new or deleted import builds a new network. The cache keeps four networks and
  evicts the least recently used one. It is guarded by a lock.
- **Scheduled only.** Every result says so. Live positions are never shown, and `realtime` is always `false`.

The search writes nothing to the database.

### Scenarios

A scenario belongs to one device, identified by the hash of its `X-Client-Key`. It has an origin, a destination, optional
intermediate stops, a route number, a year (2027 to 2030), a frequency and operating days. Its estimate is calculated from
those values and the configured assumptions:

- distance: the straight-line length through the points in order (haversine), multiplied by the road detour factor
  (`DETOUR_FACTOR`, 1.3 by default);
- journey time: the distance divided by `AVG_BUS_SPEED_KMPH` (15 km/h by default), plus `STOP_DWELL_MINUTES` (0.5 by default)
  for each intermediate stop;
- departures per day: the number of frequency steps from the first departure to the last, rounded down, plus one; departures
  per week: that number times the operating days.

These defaults are placeholder assumptions to be calibrated, not measured data, and each estimate carries a note that says so.
A warning is added when the scenario's route number matches a route in verified official data for the same year. Without coordinates for every point, distance and journey time are not estimated, and the answer asks for them. Scenarios can
be compared side by side and exported as CSV or PDF.

### Administration

An administrator enters the administrator key in the Administration page. The page keeps it in memory and sends it in the
`X-Admin-Key` header with each administrative request. From that page the administrator can upload a feed, create a data
source, verify or revoke an `OFFICIAL` source, delete an import with its timetable and fare rows, create a backup, and read the
audit log.

The command-line tools can import a feed, and verify or revoke its source with `--verify` or `--revoke`. They also back up the
database. Their imports and source changes write audit entries with the actor `cli` and no client address. The backup script
writes and verifies the backup file, but it does not write an audit entry; the administration backup does.

## Time zone, clock and languages

- **Service time zone.** `service_zone` (`services/schedule.py`) uses the agency time zone of the loaded feed. With no feed it
  uses `SERVICE_TIMEZONE` (`Asia/Kolkata` by default). Where the operating system has no IANA time zone database, `zoneinfo`
  uses the `tzdata` package. `requirements.txt` sets a minimum (`tzdata>=2024.1`), and `requirements-verified.txt` pins the
  tested version (`tzdata==2026.6`).
- **Clock.** `/api/clock` gives the current time in UTC and local time in the service time zone, the service date and weekday, and a feed status for each classification, one of `NO_FEED` (no completed import), `COVERS_TODAY`, `GAP_TODAY` (feeds exist, none covers today, and some have ended while others have not started), `EXPIRED` (all have ended) or `NOT_STARTED` (all start later). The dashboard's clock reads this endpoint, so it shows the service area's local
  time, not the time zone of the phone or computer.
- **Languages.** `dashboard/i18n.js` has one dictionary per language: English, Kannada, Telugu and Hindi. On start-up the
  dashboard uses the language saved under `bmtc.lang`. Failing that, it uses the first language in the browser's
  `navigator.languages` that the dashboard supports, and then English. Each script's font stack is chosen from the page's
  `lang` attribute.
- **Translated text.** The dashboard's own text comes from `i18n.js` by key, and the static tests check that each key the code
  uses exists in all four languages. The dashboard also translates the title of each year banner, the scenario notice, the backup confirmation, the non-affiliation notice in the footer, and the messages that come with the
  codes listed in `docs/TRANSLATION.md`. The server's other messages are in English. These include the year-coverage sentences
  under the banners, the feed checker's errors and warnings, and API error details. The CSV and PDF exports are in English.
  The PDF writer cannot draw Hebrew, Arabic, Indic or Southeast Asian scripts, so it replaces those characters with `?` and
  the PDF says so in a notice. The CSV keeps the full text.

## Installable app and offline use

- **Manifest.** `dashboard/manifest.webmanifest` gives the name, the short name "Transit Planner", the start URL `/`, the
  language `en`, standalone display, and the 192 and 512 pixel icons.
- **Service worker.** `dashboard/sw.js`, version 3, is registered from the page at start-up. Browsers allow a service worker and
  installation only over HTTPS, or on `localhost`. The dashboard ignores the error when a browser refuses.
  - The **shell** (the page, scripts, styles, manifest, icons and Leaflet) is fetched from the network first and then stored,
    so a new version is used at once. When the network fails, the stored copy is used, and a navigation with no stored copy
    gets the stored page.
  - **Public timetable answers** are kept in a separate cache of up to 120 answers, and the oldest are dropped first. Kept are
    the answers for the list of routes, one route, a route's timetable, the list of stops and the list of data sources. The
    worker answers from the network and keeps a copy of each successful answer. When the network fails, it returns the copy
    with the header `X-Served-From-Cache: 1`. Each copy carries `X-Saved-At`, the time it was saved.
  - **Never kept.** Every other `/api/` request goes to the network: journeys, plans, nearby stops, departures, the clock, the
    metadata, scenarios, saved routes, preferences and administration. So does a route or stop search that has typed words in
    its `q` parameter, and such a search is never kept. A request whose `q` is empty or missing is kept.
  - The worker deletes the older caches of either kind when it is activated. Requests to other origins, such as map tiles, are
    left alone.

## Deployment kit (not built in this build)

- **`Dockerfile`.** Builds from `python:3.13-slim` (a tag, not a digest). It installs `requirements.txt` with
  `requirements-verified.txt` as constraints, so each package stays at the tested version. It runs as the user `planner`
  (uid 10001) and keeps the database and backups in the `/app/data` volume. It sets `DATABASE_URL`, `BACKUP_DIR` and
  `FORWARDED_ALLOW_IPS=127.0.0.1` as defaults. Its health check calls `/api/health`. It starts uvicorn with `--proxy-headers`,
  so the client address is taken from `X-Forwarded-For` only from the addresses in `FORWARDED_ALLOW_IPS`.
- **`docker-compose.yml`.** The `planner` service publishes no port, drops all Linux capabilities (`cap_drop: ALL`), sets
  `no-new-privileges`, and sets `FORWARDED_ALLOW_IPS` to Caddy's fixed address. The `caddy` service (image `caddy:2`) publishes
  ports 80 and 443 over TCP and 443 over UDP. Both services sit on a private network with fixed addresses (`172.28.0.10` and
  `172.28.0.20`). `PLANNER_DOMAIN` is required: Compose fails to parse the file without it.
- **`deploy/Caddyfile`.** Serves `PLANNER_DOMAIN` over HTTPS, compresses responses with zstd and gzip, sends
  `Strict-Transport-Security` with `max-age=15552000` (180 days), and reverse-proxies to `planner:8000`. It has no `log`
  directive.
- **Status.** The Compose file was validated with a placeholder domain. The image was not built: the build sandbox's proxy
  returned `403 Forbidden` for the Docker Hub registry, and no Docker daemon was reachable in the final check. Caddy was not
  run. See `docs/DEPLOY.md`.

## Security model

| Layer | What it does |
|---|---|
| Rate limiter | Counts requests per client address on `/api/` paths and returns 429 after `RATE_LIMIT_PER_MINUTE` (120 by default) in a 60-second window. It tracks up to 10,000 active clients and refuses new ones beyond that, so a flood of addresses cannot reset the counts of the clients already tracked. |
| Security headers | On every response: `X-Content-Type-Options: nosniff`, `X-Permitted-Cross-Domain-Policies: none`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`, `Cross-Origin-Opener-Policy: same-origin`, and a `Permissions-Policy` that allows geolocation for the page only (`geolocation=(self)`) and turns off camera, microphone, payment and USB. `Cross-Origin-Resource-Policy` is `same-site` for the API and `same-origin` for the dashboard. |
| Dashboard policy | On dashboard responses: `default-src 'self'`, `object-src 'none'`, `script-src 'self'` (no inline script and no `eval`), `style-src 'self' 'unsafe-inline'`, `img-src 'self' data:` plus the OpenStreetMap tile host, `connect-src 'self'`, `manifest-src 'self'`, `worker-src 'self'`, `frame-ancestors 'none'`, `base-uri 'self'` and `form-action 'self'`. Non-API responses are sent with `Cache-Control: no-cache`. |
| Administrator key | Sent in `X-Admin-Key` and compared with `hmac.compare_digest`. With `ADMIN_API_KEY` empty, every administrative route returns 503. A wrong or missing key returns 401. A key shorter than 32 characters still works, and the server logs a warning. |
| Device key | Sent in `X-Client-Key`. It must be 16 to 128 characters of letters, digits, `_` and `-`. Only its SHA-256 hash is stored. |
| Input checks | Pydantic schemas validate request bodies and query parameters. GTFS checks reject hostile archives and bad fare files. Uploaded file names are reduced to safe characters. Search text escapes `\`, `%` and `_`, so they match literally. |
| Output checks | A CSV cell that a spreadsheet would read as a formula gets a leading apostrophe. That applies to cells starting with `=`, `+`, `-`, `@`, a tab, a carriage return or a line break, after any leading spaces or invisible characters. PDF text escapes `&`, `<` and `>`. The dashboard builds its HTML with an escaping helper and sets text with `textContent` where it can. |
| Queries | Application queries use SQLAlchemy with bound values. Raw SQL is limited to the `PRAGMA` settings in `database.py` and, in `maintenance.py`, fixed statements: reads of `sqlite_master` and `alembic_version`, the integrity and foreign-key checks, the journal-mode setting of each backup copy, and a `SELECT 1` connection check. The row counts are built by SQLAlchemy from the model metadata. |
| Credentials | The keys travel in request headers (`X-Admin-Key`, `X-Client-Key`), not in cookies or URLs. The application sets no cookies. CORS is off unless `CORS_ORIGINS` is set. |
| Audit | These actions write an `audit_logs` entry: `data_source.create`, `data_source.verify`, `gtfs.import`, `gtfs.import_rejected`, `gtfs.import_failed`, `gtfs.delete`, `database.backup`, `scenario.create`, `scenario.update` and `scenario.delete`. Saved routes and preferences are not audited. Entries that come through the API record the client address. Command-line entries do not. Scenario changes made by a device record the actor `device:` followed by the first 12 characters of the hash of its key. Administrator actions record `admin`. A revocation is logged as `data_source.verify` too, with `verified` set to `false` in its detail. |

### Limits of the security model

- The application does not terminate TLS. Over plain HTTP the administrator key and device keys travel unencrypted.
- There is no lockout after failed administrator attempts, and no key rotation. Use a long random administrator key. Changing
  it needs a restart.
- A device key is a bearer credential. Anyone who has it, or the browser profile that holds it, can use that device's
  scenarios and saved routes. A device key does not expire, and the user cannot revoke it except by clearing the site's data.
- The device key is kept in the browser's `localStorage`. The administrator key is kept only in the page's memory.
- The rate limiter lives in one process's memory. Several worker processes would each keep their own counts.
- The application never reads `X-Forwarded-For` itself. uvicorn does, and only from the addresses in `FORWARDED_ALLOW_IPS`,
  which default to `127.0.0.1`. Any other reverse proxy needs the same setting, or every client appears to come from the
  proxy's address, and both the rate limit and the audit addresses refer to the proxy.
- `style-src` allows inline styles. Scripts may not be inline.
- No code path deletes audit entries, and the one audit-log query only reads them.
- uvicorn's access log keeps query strings, so journey and plan searches, route and stop searches, and the coordinates of "stops
  near me" appear in it. `docs/PRIVACY.md` describes this.
- The API documentation at `/api/docs` and the OpenAPI file at `/api/openapi.json` are public. ReDoc is turned off.

## Dashboard

The dashboard is a single page with hash routes: `#/routes` (with `#/routes/<id>` for one route), `#/stops` (with
`#/stops/<id>`), `#/journey`, `#/scenarios`, `#/compare`, `#/sources` and `#/admin`. It has no build step and no framework.

- It stores the device key, the chosen year, the classification and the language in `localStorage`, under the prefix
  `bmtc.`. The administrator key is never stored.
- On a phone the page shows a menu button, and no page scrolls sideways. Both are checked in the browser suite, which also
  checks that the offline timetable is kept and that a search with typed words is not.
- The map tiles come from OpenStreetMap. The browser suite loads the map. The tiles themselves could not be loaded in the build
  sandbox, so their display was not checked.

## Tests

| Area | Files | What they cover |
|---|---|---|
| Journey planning | `tests/test_planner.py`, `test_plan_api.py`, `test_fares.py`, `test_planner_performance.py` | Direct and one-change journeys, two changes, the minimum change time, walks of about 200 metres and not about a kilometre, walking switched off, trips after midnight, now mode, a stop with no connection, an official plan that never uses unverified data, a changed import changing the answer, fares (a route fare, a zone fare not shown as a route fare, fares never added across changes, malformed fare files rejected), and timing limits on a generated feed of 2,000 stops. |
| Timetables and clock | `tests/test_schedule.py`, `test_clock.py`, `test_now_api.py` | Coverage messages, operating days, holidays, departures, direct journeys, the service clock, trips past midnight, and the now-mode API. |
| API and security | `tests/test_api.py`, `test_openapi.py`, `test_hardening.py`, `test_security.py`, `test_security_headers.py`, `test_rate_limit.py`, `test_trusted_proxy.py`, `test_config.py` | Administrator gating (503 without a key, 401 with a wrong one), upload limits, verification with evidence, the audit log, device scoping of saved routes, scenarios and preferences, the backup endpoint, the 429 response, the security headers, proxy trust, the published status codes and settings. |
| Search and text | `tests/test_search.py`, `tests/test_text_and_search.py` | Literal matching of `%`, `_` and `\`, case folding, spacing and Unicode normal forms. |
| Import and command line | `tests/test_gtfs_importer.py`, `test_importer_regressions.py`, `test_cli.py` | GTFS rules, path traversal, absolute and duplicate members, the compression, size and member-count limits, times past midnight, time zone rules, import reports, the command-line actor and exit codes. |
| Scenarios and exports | `tests/test_scenarios.py`, `test_exports_and_pdf.py` | Estimate arithmetic, owner scope, CSV and PDF output, formula neutralising, and the PDF notice for characters that cannot be drawn. |
| Migrations and maintenance | `tests/test_migrations.py`, `test_maintenance.py` | A new database reaches the head revision and matches the models, and the migration can be reversed. A database built before migrations is stamped and keeps its rows. Backups are verified, failed copies are deleted, and the check never creates a missing database. |
| Dashboard, static | `tests/test_dashboard_static.py` | Translation dictionaries (same keys, placeholders, no copied English, every message code translated), font rules, storage rules, no inline script and no code built from strings, the service worker's allowlist and privacy rule, and the manifest. |
| Windows launchers | `tests/test_windows_launchers.py` | Five launchers are present. Each is plain ASCII with Windows line endings, and each refers only to scripts and requirements files that exist. The tests do not run the launchers. |
| Browser | `tests/browser/` | Headless Chrome through Playwright, a desktop viewport and a Pixel 7 device profile, with axe-core 4.14.0 for the WCAG 2.0 and 2.1 A and AA rules and the best-practice rules. |
| Mutation | `tests/mutation/` | Breaks safety rules one at a time in temporary copies. Each broken copy must make a test fail. Run by hand, not by `pytest`. |
| Restore drill | `scripts/restore_drill.sh` | 29 checks in six sections, run on a temporary copy of the project: the command-line tools answer `--help`; a new database is migrated and checked; a synthetic demo feed is imported, and the importer refuses to verify it; refusals and rejections happen as documented; a verified backup is taken, the database is damaged, and the backup is restored and checked; the server starts on the restored database and reads it back. Bash on Linux only. |
| Android starter | `android/check_starter.py` | Static checks of the YAML and Dart files. It does not compile the app. |

The results of the final run are in `docs/TEST_RESULTS.md`.

## Known structural limits

- One process and one SQLite file are assumed. Several worker processes would need a shared rate-limit store, and SQLite under
  heavy concurrent writes has not been load-tested.
- PostgreSQL is reachable through SQLAlchemy in principle, but it is not tested. The administration backup works only for
  SQLite, and returns 501 on PostgreSQL.
- The planner has no background jobs. Nothing is pruned, and nothing refreshes an import automatically.
- Live bus positions and delays are not shown, because no authorised live feed is connected.
- Only the synthetic demonstration feed was loaded in testing. No real timetable feed from any city has been tested.
- **Namma Metro is not supported.** No metro data is included, and the planner has no metro-specific logic. It stores each
  feed's route type and shows it in route listings, but it does not use it when it plans a journey. A metro feed would need
  its own source record, its own check of its terms, and the same import and verification steps as a bus feed.
- Overlapping imports of one classification are both kept and searched, so a route can appear twice. The import reports a
  warning.
- Journey planning has been measured only on a generated feed, so its timings on a real network are not known.
- Four languages are included: English, Kannada, Telugu and Hindi. All Kannada, Telugu and Hindi text is a first draft.
  Right-to-left languages have not been added or tested. The stylesheet uses physical left and right properties in places,
  so a right-to-left language would need a layout check first.
- The Docker and Caddy kit has not been built or run in this build.
