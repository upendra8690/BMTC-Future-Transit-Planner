# BMTC Future Transit Planner

A planning tool for Bengaluru bus services for 2027 to 2030. It shows three kinds of information, and keeps them apart:

- **Officially verified timetables**, only when an administrator has verified an official source;
- **Unverified feeds**, labelled as such;
- **Estimated scenarios**, which are proposals with labelled assumptions, never official announcements.

This is not an official BMTC product, and it does not contain official BMTC timetable data. See "Data" below.

## Status

**Working and tested in this build**

- Timetable browsing by route and date, route and stop search, direct journeys, and CSV export of timetables.
- Owner-scoped future scenarios with transparent estimates, side-by-side comparison, and CSV and PDF export.
- GTFS import from the command line and from the Administration page, with hostile-archive checks, a duplicate warning,
  and a `COMPLETED` or `REJECTED` record for each feed that reaches validation.
- Verification and revocation of `OFFICIAL` sources, with an audit trail.
- Verified SQLite backups, a database check, and Alembic migrations.
- 35 API operations, documented in `docs/API.md` and at `/api/docs` while the planner runs.
- Automated tests and browser checks. Results are in `docs/TEST_RESULTS.md`.

**Not done, or not verified**

- No official BMTC timetable is loaded, and none is shown for 2027 to 2030. See `SOURCES.md`.
- No Android APK is built. The Flutter starter is not compiled. See `android/README.md`.
- Nothing has been run on a real phone. Browser checks ran in headless Chrome with a Pixel 7 device profile.
- The Windows `.bat` launchers have not been run on Windows. Their commands were checked against the code.
- All checks ran on Linux with Python 3.13. Python 3.11, Python 3.12 and Windows have not been tested.
- PostgreSQL is not tested. Only SQLite is.
- HTTPS hosting for public use is not built. See `docs/PHONE_ACCESS.md`.
- No licence has been chosen for this project.

## Quick start on Windows

Follow `docs/INSTALL_WINDOWS.md`. In short: run `scripts\setup_windows.bat` once, set `ADMIN_API_KEY` in `.env`, then
run `scripts\run_windows.bat` and open `http://127.0.0.1:8000/`.

## Quick start for developers (any system)

```
python -m venv .venv
. .venv/bin/activate                       # Windows: .venv\Scripts\activate
python -m pip install -r requirements-dev.txt
cp .env.example .env                       # Windows: copy .env.example .env, then set ADMIN_API_KEY
python scripts/migrate_database.py
python -m pytest
python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000
```

For the exact package versions used in the Linux checks, install `requirements-verified.txt` instead of
`requirements-dev.txt`. That file is for Linux only.

Browser checks, optional:

```
python -m pip install -r requirements-browser.txt
python -m playwright install chromium       # or pass --chrome with an installed Chrome
python tests/browser/run_browser_checks.py
```

The runner builds a temporary demo database, starts its own server, runs 36 checks, and stops the server. It does not
touch your `data/` folder.

Mutation checks, optional (a few minutes):

```
python tests/mutation/mutation_check.py
```

It breaks five safety rules one at a time, in temporary copies, and confirms that the tests fail for each one.

## What the planner shows

| Classification | Meaning |
|---|---|
| `OFFICIAL_VERIFIED` | Data from an `OFFICIAL` source that an administrator has verified. Empty until that happens. |
| `UNVERIFIED_FEED` | Data from any other source. Shown separately and labelled. |
| `ESTIMATED_SCENARIO` | A proposal, with its distance, journey time and frequency calculated from labelled assumptions. |

For each planning year (2027 to 2030) the planner states whether a classification covers the whole year, part of it, or
none of it. When there is no officially verified timetable it says: "No officially verified timetable is available for
this future year."

## Data

- **No official BMTC data is included.** The official candidate, the DULT Transport Data Hub, could not be reached from the
  build environment, and its licence was not found. `SOURCES.md` lists what was reviewed and why each community feed was
  not used.
- **The synthetic demo feed** (`scripts/make_synthetic_gtfs.py`) is invented. Its routes, such as `DEMO-1`, are not BMTC
  routes. It is for testing only.
- **Scenario estimates** use placeholder assumptions: 15 km/h average speed, 0.5 minutes dwell per stop, and a road
  detour factor of 1.3. They are labelled in every result and should be calibrated against real data before anyone relies
  on them.

## Documentation

| Document | For |
|---|---|
| `docs/INSTALL_WINDOWS.md` | Installing, running, loading data, backups and restore on Windows |
| `docs/PHONE_ACCESS.md` | Opening the planner on phones, what works over plain HTTP, and what HTTPS hosting would need |
| `docs/API.md` | The API: rules, authentication, examples |
| `docs/architecture.md` | Components, data flow, classifications, security model and its limits |
| `docs/TEST_RESULTS.md` | What was run to verify this package, with the real output |
| `database/README.md` | Tables, migrations, checking, backups and restore |
| `android/README.md` | The Flutter starter, its build steps and its limits |
| `SOURCES.md` | Data sources, what was reviewed, and what must happen before official data is used |

## Repository layout

```
backend/app/        application: API, services, GTFS importer, security, database
dashboard/          web dashboard (HTML, CSS, JavaScript), service worker, manifest, vendored Leaflet
scripts/            command-line tools and Windows launchers (.bat files use CRLF line endings)
migrations/         Alembic migrations (baseline 0001 creates the 16 tables)
tests/              automated tests; tests/browser/ holds the browser checks; tests/mutation/ holds the mutation check
docs/               guides and test results
database/           database guide
android/            Flutter WebView starter (not built)
```

## Security in brief

- The administrator key is required for uploads, verification, backups and the audit log. With no key set, those
  routes are disabled, and they return 503.
- Each device is identified by a key it sends in the `X-Client-Key` header. The planner stores only the SHA-256 hash of
  that key.
- The API is rate limited per client IP. The dashboard is served with a Content Security Policy.
- Plain HTTP is the default. Anyone who can read the network traffic can read the keys. Use HTTPS before any use beyond
  a trusted network.

`docs/architecture.md` lists the limits of this model, including the ones that matter for a public deployment.

## Verification summary

Full details and output are in `docs/TEST_RESULTS.md`.

- Automated tests: 159, all passing on Linux with Python 3.13 in a fresh virtual environment.
- Browser checks: 36, all passing on Linux with Chrome, against a server with synthetic demo data.
- Lint: `ruff check .` passes.
- Security: `bandit` reports no issues. Seven intentional suppressions remain, each with a reason in the code.
  `pip-audit` finds no known vulnerabilities in the exact versions in `requirements-verified.txt`, nor in the version
  ranges of `requirements-dev.txt` and `requirements-browser.txt`.
- Mutation checks: five deliberately broken safety rules, and the tests caught all five.
- Restore drill: on Linux, a verified backup was made, the database was damaged on purpose, and the backup was restored
  and checked. The server then answered from the restored database.

## Licence

No licence has been chosen for this project, so no licence file is included. The vendored Leaflet 1.9.4 is under the
BSD 2-Clause licence, and its licence file is in `dashboard/vendor/leaflet/`. Other dependencies have their own licences.
