# Repository audit: Bengaluru Transit Planner 4.0

Audit of branch `v4` on 19 November 2026, including the Phase 2 changes in the same commit as this file. Status labels
used everywhere in `docs/audit/`:

| Label | Meaning |
|---|---|
| **IMPLEMENTED AND TESTED** | Works, with an automated or browser test recorded below |
| **IMPLEMENTED BUT NOT FULLY VERIFIED** | Code exists and has tests, but has not run where it will be used (for example on a phone) or is switched off |
| **DEMONSTRATION ONLY** | Works only on a demonstration server (`DEMO_MODE=1`) with invented data, labelled on every screen |
| **WAITING FOR OFFICIAL API/PERMISSION** | Needs official data, an agreement or credentials; the app says so instead of failing |
| **NOT IMPLEMENTED** | Does not exist |

## A. Current architecture
One FastAPI server (Python 3.12/3.13, SQLAlchemy 2, Alembic) serves a JSON API (71 operations) and a plain-JavaScript
progressive web app. Data is GTFS imported into SQLite (free hosting) or PostgreSQL (proven in CI). An Android Flutter
WebView wrapper is built by CI. The public service runs on Render from `v4`, separate from 3.0 on `main`. Details:
[SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md).

## B. Features that work today
| Feature | Status | Evidence |
|---|---|---|
| Namma Metro journeys (Purple, Green, Yellow), up to two changes, walking transfers | IMPLEMENTED AND TESTED (community data, labelled "Unverified feed", approximate times) | pytest; `real_mode_check.py` 14/14; public deployment check |
| Metro station directory, line pages, timetables | IMPLEMENTED AND TESTED (same data) | `real_mode_check.py`; e2e |
| Nearby stops and stations ("Stops near me") | IMPLEMENTED AND TESTED; entrances and duplicate platform entries removed in this audit | `test_nearby_lists_each_station_once_and_never_an_entrance` |
| **New:** service notices (administrator-posted, official sources only, dated, audited) | IMPLEMENTED AND TESTED | `tests/test_notices.py` (22 tests); `phase2_check.py` |
| **New:** quick destinations (major Metro stations present in the data) | IMPLEMENTED AND TESTED | `phase2_check.py` |
| **New:** swap start and destination; start from my location; shareable journey links | IMPLEMENTED AND TESTED | `phase2_check.py` (18/18) |
| Upcoming transport register with status, sources and change history | IMPLEMENTED AND TESTED | pytest; `upcoming_admin_check.py` 17/17 |
| Four languages (English, Kannada, Telugu, Hindi; 680 texts each) | IMPLEMENTED AND TESTED (translations not reviewed by native speakers) | key-parity test; launch check |
| Offline shell and saved timetables; installable PWA | IMPLEMENTED AND TESTED in Edge; device install not tested | e2e |
| Favourites, saved journeys, recent searches (on the device) | IMPLEMENTED AND TESTED | e2e |
| Emergency numbers (112, 108, 101, 1098) | IMPLEMENTED AND TESTED (web) | e2e |
| Administration: GTFS import with validation, source verification, backups, audit log | IMPLEMENTED AND TESTED | pytest; e2e |
| Passenger accounts, roles, recovery codes | IMPLEMENTED BUT NOT FULLY VERIFIED (server only; switched off until PostgreSQL) | `tests/test_accounts.py`; CI PostgreSQL job |
| Android wrapper (location on request, retry, downloads, API 36, AAB) | IMPLEMENTED BUT NOT FULLY VERIFIED (compiles in CI; never run on a device) | CI `d72e5c9` |
| Bus routes, stops, timetables, bus and combined journeys | DEMONSTRATION ONLY (no real bus data) | e2e on a demonstration server |

## C. Missing Namma BMTC 2.0 capabilities
Live tracking and arrival times, bus data, tickets, passes, Metro QR, payments and ticket history are missing. Every one
of them needs official data or an agreement. Feature by feature: [FEATURE_GAP_ANALYSIS.md](FEATURE_GAP_ANALYSIS.md).

## D. Security risks
No known high-severity issue. Open: one shared admin key (S5, medium), no permanent database or backups on free hosting
(H1, medium), Android not tested on a device (A1, medium), CSP allows inline styles (S4, low). No independent
penetration test. Details: [SECURITY_AUDIT.md](SECURITY_AUDIT.md).

## E. Official integrations required
| Integration | From whom | Status |
|---|---|---|
| Static bus and Metro timetables (GTFS) and licence | DULT (Transport Data Hub) or BMTC / BMRCL | WAITING FOR OFFICIAL API/PERMISSION; requests drafted (`government_submission_2026/15`–`17`) |
| Live vehicle positions, arrival predictions, alerts (GTFS-Realtime) | BMTC | WAITING FOR OFFICIAL API/PERMISSION |
| Fares | BMTC, BMRCL | WAITING FOR OFFICIAL API/PERMISSION |
| Bus tickets and passes | BMTC | WAITING FOR OFFICIAL API/PERMISSION |
| Metro QR tickets | ONDC and BMRCL | WAITING FOR OFFICIAL API/PERMISSION |
| Payments | An RBI-authorised payment aggregator | WAITING FOR OFFICIAL API/PERMISSION |
| NCMC | An issuing bank and the operator | WAITING FOR OFFICIAL API/PERMISSION |

## F. Prioritised plan
See [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md). Next, with no permission needed: Android device testing,
accounts screens (once a permanent database exists), inline styles out of the CSP, and a GTFS-Realtime ingestion adapter
that stays off until a feed is authorised.

## Placeholders and demonstration data
- **Invented data:** two demo feeds, served only when `DEMO_MODE=1`; the public service never serves them (tested).
- **Provider adapters:** one per capability (live vehicles, tickets, passes, Metro QR, payments, NCMC); each refuses with
  HTTP 503 and names the official channel. No ticket, QR code, receipt, balance or vehicle position is ever produced.
- **No dead buttons:** every Home tile opens a screen; unavailable features explain why (`/api/features`).
- **Hard-coded values:** emergency numbers and official links (checked and dated); the quick-destination station names
  (shown only if present in the data).

## Environment and integrations
Variables are documented in `.env.example` and `docs/launch/DEPLOYMENT_GUIDE.md`: `DATABASE_URL`, `ADMIN_API_KEY`,
`DEMO_MODE`, `LOAD_COMMUNITY_METRO`, `SEED_DEMO_FEED`, `ACCOUNTS_ENABLED`, `RATE_LIMIT_PER_MINUTE`, `CLIENT_IP_HEADER`,
`EPHEMERAL_STORAGE`, `FORWARDED_ALLOW_IPS`, `CORS_ORIGINS`, `SERVICE_TIMEZONE`, `PDF_FONT_PATH`, `LOG_LEVEL` and upload
limits. The only outside service the app calls is the OpenStreetMap tile server (from the browser).

## Test results on this commit (19 Nov 2026, Windows, Python 3.12, Edge)
| Suite | Result |
|---|---|
| ruff | All checks passed |
| bandit (medium and high) | No issues |
| pytest | **535 passed, 5 skipped, 0 failed** (the skips need the DejaVu Sans font) |
| `tests/browser/phase2_check.py` (new features, local real-mode server) | 18 of 18 |
| `tests/browser/real_mode_check.py` | 14 of 14 |
| `tests/browser/responsive_check.py` (320 to 1920 px) | 22 of 22 |
| `tests/browser/upcoming_admin_check.py` | 17 of 17 |
| `tests/audit/audit_a11y.py` (axe, WCAG 2.1 AA) | No violations on 15 screens in 2 themes |
| GitHub Actions CI (Python 3.12 and 3.13 with ruff, bandit, pip-audit; containers; PostgreSQL) | 4 of 4 jobs passed on `1646d66`, push and pull request |
| Public service after deployment (`verify_deployment.py`, `real_mode_check.py`) | All checks passed; 14 of 14; `/api/notices` live; nearby search near Cubbon Park lists only "Cubbon Park" |

## Defect found and fixed in this audit
**"Stops near me" listed station entrances and duplicate platforms.** Near Cubbon Park it showed the station three
times and five entrances; "Use my location" would have chosen an entrance, which no journey can start from. Nearby
search now leaves out entrances (GTFS `location_type` 2 to 4) and lists each station once. A regression test fails on
the old code and passes on the new.
