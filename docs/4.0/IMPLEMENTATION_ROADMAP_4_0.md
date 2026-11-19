# Implementation roadmap: Bengaluru Transit Planner 4.0

Every phase ends with: tests, lint, a security review of the change, updated docs, an honest report (done / awaiting
provider / planned / unavailable / demo-only), and commits on the `v4` branch. `main` keeps serving 3.0 until release.
The app stays deployable after every stable phase.

Status labels used in all reports: **Implemented and tested**, **Implemented, awaiting provider access**, **Planned**,
**Unavailable**, **Demo-only**.

**Progress:** Phase 0 done · Phase 1 done (4.0.0-alpha.1) · Phase 2 done (4.0.0-alpha.2) · Metro stations and bus + Metro journeys (parts of Phases 4 and 7) done on demo data · Phase 5 (accounts) next. See `PHASE_REPORTS.md`.

| Phase | Scope | ₹0? | Blocked parts | Owner actions |
|---|---|---|---|---|
| 0 | Audit and plans (these documents) | Yes | — | Decisions made 16 Nov 2026 |
| 1 | Mobile-first app: rename to Bengaluru Transit Planner, animated splash, search-first home, map card, 9-section navigation (Home, Nearby, Plan Journey, Live Tracking, Tickets and Passes, Metro, Favourites, My Account, More Services), light/dark mode, low-data mode, large-text option, loading/empty/offline/error states, `/api/features`, translation keys + review checklist | Yes | — | Review screenshots |
| 2 | Bus: routes by number and destination, first/last service, stop details with routes served, stop-wise scheduled arrivals, directions to stops (walking link), journey planner from current location, walk distances, transfer instructions, fare display, bus categories when the data confirms them, service alerts (admin-entered with source), accessibility fields (`0003`); live tracking screen with honest "unavailable" state | Yes (demo data) | Real data (DULT); live feed | Download the DULT feed + terms |
| 3 | Namma BMTC 2.0 capability comparison (in `FEATURE_MATRIX_4_0.md`) and provider adapter framework: interfaces + states for realtime, tickets, passes, payments, notifications | Yes | Every activation | Optional: ask BMTC about aggregator data sharing |
| 4 | Metro module: station directory and search, lines and colours, interchanges, station map, first/last train and hours from GTFS, fares from GTFS, announcements (cited), Metro and bus↔Metro planning with walking links, airport connectivity (cited); ticket screens in "unavailable" state with official channels; NCMC information page | Code yes | Metro data licence; QR ticketing (ONDC, business); NCMC operations | Confirm Metro data source |
| 5 | Accounts on Neon Postgres: register, login, logout, password reset, argon2id, sessions, CSRF, roles, profile, favourite routes/stops, saved journeys, recent searches, notification preferences, deletion, export, pooling, backup/restore procedure | Yes | Password-reset email needs an email provider (free tier possible) | Create Neon DB; choose email provider |
| 6 | Tickets, passes, payments: ticket/pass/history/refund screens, provider and payment adapters, server-side verification, signed webhooks, idempotency, audit trail; tested only against a fake gateway in tests | Architecture yes | Ticketing agreement and gateway KYC | Only with a registered business |
| 7 | Multimodal planner: fastest, fewest transfers, lowest cost (when fares exist), accessible journeys, waiting times, provenance per leg (scheduled / live / estimated) | Yes | Real feeds | — |
| 8 | Future services: a curated directory of **official links** (railways, airport, cabs/autos, hotels, temples' official booking, hospitals, government services) plus OSM-based parking, EV charging, toilets, water, accessibility; traffic info only from an authorised source | Links + OSM yes | Any booking integration; traffic data | — |
| 9 | Maps and location: layers (stops, stations, facilities, vehicles when live), journey polylines, permission handling, manual search, configurable tile provider, server-side geocoding | Yes (light use) | High-volume tiles/geocoding | — |
| 10 | Notifications (Web Push: disruptions, saved-route changes, reminders) and AI assistant (rule-based default in 4 languages; optional LLM adapter; answers only from app data with timestamps) | Yes (rule-based, Web Push) | LLM (paid, optional) | Optional API key |
| 11 | Admin: user management, role-based access, data-source and licence registry, imports and GTFS validation, feed expiry monitoring, service and integration health, audit and security event logs, backup status | Yes | — | — |
| 12 | OWASP-based security assessment with findings, evidence, remediation and retests | Yes | Professional pen test (paid) | — |
| 13 | Android shell (back button, location permission, network errors, secure WebView, deep links, lifecycle, offline screen, release signing, APK + AAB workflows); PWA update notice; iOS evaluation (PWA on iPhone is free; a native iOS build needs a Mac and the Apple Developer Program) | Android/PWA yes | Release key (owner); iOS distribution (paid) | Create signing secrets |
| 14 | Full test run, load and smoke tests, docs, CHANGELOG, `RELEASE_NOTES_4_0.md`, screenshots, `BENGALURU_TRANSIT_PLANNER_4_0.zip`, merge to `main`, tag `v4.0.0` | Yes | — | Final review |

## Notes on order
- Phase 1 is the foundation for every later screen; Phases 2, 4, 7 and 9 build on the existing planner and importer.
- Phase 5 must not go live before the Neon database exists, or accounts would be lost on restart.
- Phase 8 is deliberately limited to official links and OpenStreetMap data at ₹0: no business listings, prices,
  opening hours or availability are entered by hand.

## Definition of done for a feature
1. Works end-to-end against the real API (not a mock screen).
2. Has automated tests, including the negative cases in `TEST_PLAN_4_0.md`.
3. Shows its data source and last-updated date where it shows data.
4. Has text in all four languages (machine-drafted text marked for review).
5. Is listed with its true status in `FEATURE_MATRIX_4_0.md`.
