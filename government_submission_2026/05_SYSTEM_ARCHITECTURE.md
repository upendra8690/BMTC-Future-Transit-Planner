# 05 Technical architecture

Version 4.0.0-beta.1, branch `v4`, as of 18 November 2026. Section 7 describes a **proposed** architecture for an
authorised pilot; it is not built.

## 1. Components today
```
 Passenger's phone or computer
 ┌───────────────────────────────────────────────┐
 │ Progressive web app (dashboard/)              │   Android: Flutter WebView wrapper (android/flutter_app),
 │  plain JavaScript; 4 languages (en kn te hi)  │   built by CI; shows the same web app; opens phone links
 │  service worker: offline shell and timetables │   in the dialler and official sites in the browser
 │  device storage: language, favourites, saved  │
 │  journeys, recent searches, random device key │
 └──────────────┬────────────────────────────────┘
                │ HTTPS only; JSON; device key in a header, never a cookie
 ┌──────────────▼────────────────────────────────┐        ┌─────────────────────────────┐
 │ FastAPI server (backend/app), 67 operations   │        │ OpenStreetMap tile servers  │
 │  planner: round-based search, bus/Metro/walk  │        │ (map images only)           │
 │  schedules; GTFS import and validation        │        └─────────────────────────────┘
 │  verification: only OFFICIAL can be verified  │
 │  real/demo separation (DEMO_MODE)             │        ┌─────────────────────────────┐
 │  upcoming-transport register with history     │──X──── │ Operators and providers     │
 │  provider adapters: all refuse today          │        │ (not connected: no permit)  │
 │  accounts and roles: built, switched off      │        └─────────────────────────────┘
 │  security: headers, CSP, rate limit, admin key│
 └──────────────┬────────────────────────────────┘
                │ SQLAlchemy 2; Alembic migrations 0001 to 0004
 ┌──────────────▼────────────────────────────────┐
 │ Database: SQLite on free hosting (erased on   │
 │ restart); PostgreSQL 16 proven in CI          │
 └───────────────────────────────────────────────┘
```

## 2. Technology
| Layer | Choice | Why |
|---|---|---|
| Server | Python 3.12 and 3.13, FastAPI, SQLAlchemy 2, Alembic | Widely used and typed; migrations tested in CI |
| Database | SQLite for development and free hosting; PostgreSQL through `DATABASE_URL` (psycopg 3) | No cost to develop; a standard database when hosted |
| Web app | Plain JavaScript progressive web app; Leaflet 1.9.4 maps | No build step; page, scripts and styles about 100 KB compressed, plus the map library; works offline |
| Android | Flutter WebView wrapper | One code base for web and Android |
| Packaging | Docker image; Render Blueprint (`render.yaml`) for the 4.0 service only | Reproducible; 4.0 cannot change the 3.0 service |
| Testing | pytest, Playwright browser checks, axe-core, ruff, bandit, pip-audit | See [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md) |
| CI | GitHub Actions: tests on Python 3.12 and 3.13; container in demonstration and real mode; PostgreSQL job; Android compile check | Every push is checked |

## 3. Data model, in outline
- **Data source:** publisher, address, licence and kind: `OFFICIAL`, `COMMUNITY` or `SYNTHETIC_DEMO`, plus verification
  evidence.
- **Feed:** one imported GTFS file of a source, with its validity dates. Its classification is `OFFICIAL_VERIFIED`
  only when the source is OFFICIAL and an administrator has verified it; otherwise `UNVERIFIED_FEED`.
- **GTFS tables:** agencies, routes, stops, trips, stop times, calendars, fare rules.
- **Passenger data:** saved routes and scenarios under the SHA-256 hash of a random device key. Accounts, if
  enabled: a username or email, a password hash, sessions stored as hashes, saved journeys, notification preferences.
- **Upcoming transport:** entries with status, source kind, dates and sources, plus a public change history.
- **Audit log:** imports, verification, backups, upcoming-transport changes, role changes.

## 4. Real mode and demonstration mode
| | Public service (real mode, default) | Demonstration server (`DEMO_MODE=1`) |
|---|---|---|
| Invented demonstration feeds | Never served, even if loaded | Served, with a banner on every screen |
| Community Namma Metro feed | Served, labelled "Unverified feed", approximate times, no fares | Served the same way |
| Purpose | The public preview | Presentations and development only |

## 5. How a journey is planned
1. The app sends origin, destination, date and time, travel mode, the maximum number of changes and the
   classification to `GET /api/plan`.
2. The planner runs a round-based search over the timetables of that classification, adding walking transfers between
   nearby stops and stations.
3. Every ride in the answer carries its mode, route, times, timing quality (`scheduled` or `approximate`), source and
   classification. The answer always says `realtime: false`.

## 6. How official data and providers would be connected
**Official schedules, without code changes:**
1. An administrator imports the publisher's GTFS file and records its address and licence, with kind `OFFICIAL`.
2. The import validates the feed and reports any problems.
3. An administrator compares a sample with the publisher's own source and records the evidence. Only then do its
   results show as "Officially verified".
4. Each later version is imported the same way.

**Providers, after a written agreement:** each capability has one adapter in
`backend/app/services/integrations.py`. The capabilities are live vehicles, bus tickets, passes, Metro QR, payments
and NCMC.
- Today every adapter refuses with HTTP 503, a stable code and the official channel.
- To connect one after an agreement:
  1. Write the provider's adapter.
  2. Read its credentials from the hosting environment.
  3. Test it against the provider's sandbox.
  4. Register it.

## 7. Proposed architecture for an authorised pilot (not built)
Sized for a pilot of 30 to 50 participants. A larger service needs the authority's own capacity figures; none are
assumed here.

| Concern | Proposal | Trigger |
|---|---|---|
| Hosting | One always-on web service; in India on a MeitY-empanelled cloud if the authority requires it | Gate G2 |
| Database | Managed PostgreSQL with daily backups, point-in-time recovery if offered, and a quarterly restore drill | Gate G2 |
| Official data | Scheduled job: download the published feed, validate it, import it as a new version, alert on failure or staleness | Gate G1 |
| Real-time data | A worker that polls the GTFS-Realtime feed within the publisher's rate limit and hides data older than the agreed age. Redis only if measurements show a need | Gate G4 |
| Identity | Accounts and per-person administrator roles (already built), only if the pilot needs them | Gate G2 |
| Monitoring | Uptime checks; error alerts; data-freshness alerts; logs kept only as the authority requires (see [20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md), section 6) | Gate G2 |
| Security | Fixes from [20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md); audit if required | Gate G3 |

No microservices, API gateway or message queue is proposed. Nothing measured so far needs them.

## 8. Trust boundaries
| Boundary | Control |
|---|---|
| Browser to server | HTTPS, HSTS, CSP, input validation, rate limit (finding R1 open) |
| Administrator to server | Long random key or role-based accounts; audit log |
| Server to database | Credentials in the hosting environment only |
| Server to providers | None connected; adapters refuse |
| Passenger location | Used once in the browser on tap; never stored |

## 9. Deployment today
| Environment | Address | Branch | State on 18 Nov 2026 |
|---|---|---|---|
| 4.0 public preview (service `bengaluru-transit-planner-v4`) | https://bengaluru-transit-planner-v4.onrender.com | `v4` | Running in real mode; all 12 deployment checks for 4.0 passed |
| 3.0 public demonstration | https://bmtc-future-transit-planner-3-0.onrender.com | `main` | Running; unchanged; both 3.0 checks passed |
| Pilot | — | — | Not started; needs gates G1 to G3 |
