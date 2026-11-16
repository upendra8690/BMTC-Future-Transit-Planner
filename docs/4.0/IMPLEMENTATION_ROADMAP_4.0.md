# Implementation roadmap for 4.0

Every phase ends with: tests, lint, a security review of the change, updated docs, a report of what is done and not
done, and commits on the `v4` branch. `main` keeps serving 3.0 until 4.0 is released.

| Phase | Scope | Can be fully built at ₹0? | Blocked parts | Your actions |
|---|---|---|---|---|
| 0 | Audit and plan (this set of documents) | Yes | — | Answer decisions D1, D3, D4, D-NAME |
| 1 | Mobile-first redesign: animated splash, home dashboard with tiles, top bar, bottom navigation, language selector, search, map card, loading/empty/offline/error states, `/api/features`; translation keys for new text; review checklist | Yes | — | Review screenshots |
| 2 | Bus: routes between two places, stop-wise timetable, fare calculator with per-leg breakdown, share links, "updated on" dates, accessibility fields (`0003`) | Yes (with demo data) | Real data needs D4 | Get the DULT feed |
| 3 | Maps and live-tracking architecture: map layers, nearby stops redesign, GTFS-RT adapter tested with sample files, freshness rules, server-side geocoding | Yes (adapter); live data no | BMTC realtime feed | — |
| 4 | Metro: stations, lines, interchanges, station search, Metro and bus+Metro planning, last-mile links | Yes (code) | Metro feed licence (D4) | Confirm Metro data source |
| 5 | Accounts: register/login/logout, sessions, CSRF, favourites, saved journeys, recent searches, preferences, Web Push settings, deletion, export | Yes | Persistent DB (D3) | Create free Neon database |
| 6 | Facilities (OSM import), airport buses, emergency contacts, SOS (dialler + share location), help and support | Yes | SMS/WhatsApp SOS delivery (paid) | — |
| 7 | Tickets, passes, Metro QR, payments: UI states, provider interfaces, fake gateway for tests, "where to buy" official links | Architecture yes; activation no | ONDC/BMTC agreement, payment gateway KYC | Only if you register a business |
| 8 | NCMC information module | Yes | Card operations (bank/NPCI) | — |
| 9 | AI assistant: rule-based default; optional LLM adapter | Yes (rule-based) | LLM needs a paid key (optional) | Optional API key |
| 10 | Admin: role-based accounts, data freshness, provider health, feature flags, API usage, security events; security audit | Yes | — | — |
| 11 | Release: Android shell upgrade (back, location, offline, deep links), release signing, emulator smoke test in CI, PWA privacy/terms/SEO, screenshots, release notes, `BMTC_FUTURE_TRANSIT_PLANNER_4_0.zip` | Yes | Play Store ($25) optional | Create signing key secrets |

## Order notes
- Phases 1–3 need no decisions beyond D1 and can start immediately after your answers.
- Phase 4's code can be built and tested with a synthetic Metro feed while the real feed's licence is checked.
- Phase 5 should not go live until D3 is in place, or accounts would be lost on restart.

## Definition of done for a feature
1. Works end-to-end against the real API (not a mock screen).
2. Has automated tests, including negative cases (no data, stale data, provider down, offline).
3. Shows its data source and last-updated date where it shows data.
4. Has text in all four languages (machine-drafted text marked for review).
5. Is listed with its true status in `FEATURE_MATRIX_4.0.md`.
