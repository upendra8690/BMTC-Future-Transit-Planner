# 05 System architecture

## Components
```
 Passenger's phone or computer
 ┌───────────────────────────────────────────────┐
 │ Progressive web app (dashboard/)              │   Android: Flutter WebView shell (android/flutter_app)
 │  plain JavaScript; i18n en/kn/te/hi           │   shows the same web app; opens tel: links and
 │  service worker: offline shell                │   official websites outside the app
 │  device storage: language, saved stops and    │
 │  journeys, random device key                  │
 └──────────────┬────────────────────────────────┘
                │ HTTPS, JSON (key in X-Client-Key header, never in cookies)
 ┌──────────────▼────────────────────────────────┐        ┌─────────────────────────────┐
 │ FastAPI server (backend/app), 49 endpoints    │        │ OpenStreetMap tile servers  │
 │  planner (RAPTOR-style search, bus/Metro/walk)│        │ (map images only)           │
 │  schedule, GTFS import and validation         │        └─────────────────────────────┘
 │  verification (only OFFICIAL can be verified)│
 │  registry: providers, upcoming transport      │        ┌─────────────────────────────┐
 │  integration adapters (all refuse today)      │──X──── │ Operators / providers       │
 │  security: headers, CSP, rate limit, admin key│        │ (not connected: no permit)  │
 └──────────────┬────────────────────────────────┘        └─────────────────────────────┘
                │ SQLAlchemy; Alembic migrations
 ┌──────────────▼────────────────────────────────┐
 │ Database: SQLite (development, free hosting)  │
 │ or PostgreSQL (DATABASE_URL, for a pilot)     │
 └───────────────────────────────────────────────┘
```

## Technology
| Layer | Choice | Why |
|---|---|---|
| Server | Python 3.12 and 3.13, FastAPI, SQLAlchemy, Alembic | Widely used and typed; migrations are tested in CI |
| Database | SQLite for development and tests; PostgreSQL in production via `DATABASE_URL` | No cost to develop; a standard database when hosted |
| App | Plain JavaScript progressive web app; Leaflet maps | No build step; small download; works offline |
| Android | Flutter WebView wrapper | One code base for web and Android |
| Packaging | Docker image (`Dockerfile`); Render Blueprint (`render.yaml`) | Reproducible deployment; the 4.0 staging service is kept separate from 3.0 |
| Testing | pytest, Playwright browser checks, axe-core, ruff, bandit, pip-audit | See [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md) |
| CI | GitHub Actions (`ci.yml`): tests on Python 3.12 and 3.13, then a container build and smoke test | Every push is checked |

## Data model, in outline
- **Data source:** publisher, URL, licence and kind (`OFFICIAL` or `SYNTHETIC_DEMO`), plus verification evidence.
- **Feed:** one imported GTFS file belonging to a data source, with its validity dates. Its classification is
  `OFFICIAL_VERIFIED` only when its source is OFFICIAL and an administrator has verified it. Otherwise it is
  `UNVERIFIED_FEED`.
- **GTFS tables:** agencies, routes, stops, trips, stop times, calendars and fare rules.
- **Passenger data:** saved routes and scenarios, keyed by the SHA-256 hash of a random device key. There are no names,
  contacts or locations.
- **Audit:** administrative actions such as imports, verification and backups.

## How a journey is planned
1. The app sends origin, destination, date, time, the travel mode (`all`, `bus` or `metro`), the maximum number of
   changes, and the classification to `GET /api/plan`.
2. The planner runs a round-based search over the timetables of the requested classification, adding walking
   transfers between nearby stops and stations.
3. Every ride in the answer carries its mode, route, scheduled times, data source and classification. The answer
   always says `realtime: false`.

## How official data will be connected, without code changes
1. An administrator imports the publisher's GTFS file and records the source URL and licence, kind `OFFICIAL`.
2. The import validates the feed and reports any problems.
3. An administrator checks it against the publisher's own source and records the evidence. Only then do its results
   show as "Officially verified".
4. Each later update is imported the same way. The previous feed stays available for comparison.

## How a provider integration will be connected after an agreement
Each capability (live vehicles, bus tickets, passes, Metro QR tickets, payments, NCMC) has one adapter in
`backend/app/services/integrations.py`, with `describe()` and `request()` methods.

Today every adapter is `NotAuthorised`: it returns HTTP 503 with a stable code and the official channel, and never a
ticket, QR code, receipt, balance or vehicle position.

To connect a provider after an agreement:
1. Write an adapter for that provider.
2. Read its credentials from the hosting environment, never from the code.
3. Register the adapter.
4. Test it against the provider's sandbox.

Live data would arrive as GTFS-Realtime (vehicle positions, trip updates, alerts) through the same pattern.

## Deployment
| Environment | Address | Branch | State |
|---|---|---|---|
| 3.0 public demo | https://bmtc-future-transit-planner-3-0.onrender.com/ | `main` | Running; health check returned 200 on 17 Nov 2026 |
| 4.0 staging | Created from `render.yaml`: Singapore region, health check `/api/health`, admin key generated by Render | `v4` | Not yet created; needs the owner's Render account |
| Pilot (proposed) | Paid always-on service with PostgreSQL and daily backups | — | Not started |
