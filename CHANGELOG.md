# Changelog

## Unreleased (branch `v4`): integration register, feature matrix, completion report, Android test attempt, 2026-11-20
- `docs/integrations/INTEGRATION_REGISTER.md`: every BMTC and BMRCL integration, with the required API or data,
  authorisation, contact or agreement, implementation and testing status, and the remaining dependency.
- `docs/integrations/CSM_INTEGRATION_REQUEST.md`: a draft technical integration request to BMTC's Chief Systems
  Manager. It has not been sent.
- `docs/release/FEATURE_MATRIX.md`: all 105 requirements, each with one of five statuses, its test evidence and what
  is missing.
- `docs/release/COMPLETION_REPORT_2026-11-20.md`.
- **Android:** an emulator (API 36, WHPX) was set up and booted, but the local APK build failed. pub.dev connections
  were refused on the build computer (errno 10013), so **no app test ran on an emulator or device**
  (`docs/release/ANDROID_EMULATOR_TEST.md`). The build script (`scripts/android/build_test_apk.ps1`) and the emulator
  check (`tests/android/emulator_check.py`) are committed for the next attempt.
- Full browser regression on the final code: map and policy 13/13, phase 2 18/18, real mode 14/14, widths 22/22,
  upcoming 17/17, accounts 24/24, live 15/15, sandbox payments 15/15, tickets 12/12.

## Unreleased (branch `v4`): the owner's logo as the app's brand, 2026-11-20
- **New logo** (`assets/brand/logo-source.png`, the owner's blue-and-cyan transit logo) in every place:
  - PWA icons (any and maskable), Apple touch icon, favicon (PNG and a 16/32/48 px ICO), splash screen and header;
  - Android launcher sources for CI (legacy, adaptive foreground and background, native splash);
  - every Android density in `android/launcher_icons` for review;
  - Play Store icon.

  All are made by `scripts/make_brand_icons.py`.
- The name stays Bengaluru Transit Planner, and the app stays labelled independent. `assets/brand/README.md` records
  that this is not an operator logo, and flags that its Vidhana Soudha-like building could be read as government
  backing.
- The service worker cache moves to v7, so installed apps pick up the new icons.
- **Tests:** `tests/test_branding.py` (15): sizes, transparency, safe zones, every Android density, the favicon, the
  manifest and the independence statement.

## Unreleased (branch `v4`): UPI payment architecture, sandbox environment, BMTC ticketing adapter, 2026-11-20
- **Server-side payment confirmation:** an order is paid only by the gateway's signed webhook or by the gateway's
  status API asked by this server ("Check payment status", after a restart, or `POST /api/admin/payments/reconcile`).
  Returning from a UPI app proves nothing. Unique transaction ids (`BTP...`, migration 0007); one payment attempt at
  a time; pending payments expire after 30 minutes and a late success is refunded automatically; failed refunds are
  recorded; every step is audited.
- **Razorpay adapter** (`backend/app/services/payment_providers.py`): UPI payment links (UPI Intent on phones, QR on
  desktops), single-use UPI QR codes, status checks, refunds and HMAC-signed webhooks. Merchant settings are checked
  at start-up (live keys only in production, test keys only in the sandbox, https address, secrets present). Tested
  against recorded responses only; it needs merchant onboarding to be verified.
- **Sandbox environment** for demonstration servers only (`DEMO_MODE=1`, `PAYMENT_ENVIRONMENT=sandbox`): a simulated
  gateway with a choice of outcome (approve, approve without webhook, decline, pending, time-out) and a simulated
  ticketing provider. ₹1 test amounts, no money, no QR codes, and "DEMONSTRATION ONLY — NOT VALID FOR TRAVEL" on every
  screen and receipt. It can never be combined with a production provider.
- **BMTC ticketing adapter:** refuses every call (`AWAITING_BMTC_API_SPECIFICATION`) until BMTC shares its API.
- **App:** a purchase form (only where a product can be bought), an order page that checks with the gateway on
  return, transaction ids and payment states, receipts and refunds; four languages.
- **Tests:** pytest 634 passed, 5 skipped (17 sandbox scenarios, 21 Razorpay adapter tests);
  `tests/browser/payments_sandbox_check.py` 15/15.

## Unreleased (branch `v4`): tickets and payments, integration-ready; CI fix, 2026-11-20
- **Orders, payments, issued tickets, refunds and notifications** (migration 0006) and
  `backend/app/services/commerce.py`: provider interfaces for a ticketing provider (quote, issue, cancel) and a
  payment provider (start, signed notification, refund). An order is paid only after the provider's signed
  notification for the exact amount; a ticket exists only when the provider issued it, and its QR payload is stored
  exactly as sent; a failed issue after payment is refunded automatically; each notification is processed once;
  card numbers, CVVs, UPI PINs, OTPs and passwords are refused; payment records stay when an account is deleted.
- **No provider is connected**, so every purchase answers 503 with what is needed, and histories are empty. The
  workflows are tested with test doubles that exist only in `tests/test_commerce.py`.
- **Tickets screen:** what can be bought (nothing yet) and exactly what each item needs; "My tickets and payments"
  for signed-in passengers, with receipts and refund requests once anything can be sold; four languages.
- **CI fix:** the PostgreSQL persistence check made an administrator change with the shared key while accounts were
  on, which the account change of 19 Nov now refuses. It now registers a test administrator, gives it the role with
  the key and signs in, as a real administrator would.
- **Tests:** pytest 596 passed, 5 skipped (24 in `tests/test_commerce.py`); new `tests/browser/tickets_check.py`
  12/12.

## Unreleased (branch `v4`): live-tracking subsystem (off until BMTC authorises a feed), 2026-11-20
- **GTFS-Realtime provider adapter** (`backend/app/services/realtime.py`): reads VehiclePositions and TripUpdates
  over HTTPS with an optional access header from the environment, decodes them without a protobuf library, and
  matches trips, routes and stops with the official timetable. Connecting BMTC's feed needs only settings
  (`REALTIME_*`, see `docs/integrations/LIVE_TRACKING.md`).
- **Live screen:** map and list of vehicles with route, direction, next stop, route progress, last update and
  freshness ("Live" or "Delayed"); route filter; vehicle details with every stop ahead and its live estimate, or
  its scheduled time labelled "Scheduled"; live arrivals on each stop page, labelled "Live estimate".
- **Safeguards:** without a feed every live answer is "not connected" and no vehicle is shown (the public service
  today). Positions older than 10 minutes are never shown. A test feed is refused unless `DEMO_MODE=1`, and then
  every screen says "TEST FEED — NOT REAL VEHICLES" and live tracking never counts as available.
- **API:** `GET /api/live/status`, `/api/live/vehicles`, `/api/live/vehicles/{id}`, `/api/live/stops/{id}/arrivals`.
- **Tests:** pytest 572 passed, 5 skipped (26 new in `tests/test_realtime.py`); new `tests/browser/live_check.py`
  15/15; every other browser check passes (one Kannada check now waits for the re-rendered list instead of reading
  it too early).

## Unreleased (branch `v4`): map selection and a stricter style policy, 2026-11-19
- **Choose on map** in the journey planner: tap the map (or list stops near its centre) to see the nearest stops and
  stations in the chosen data, with distances, then "Start here" or "Go here". Places come only from the loaded data.
- **Security finding S4 fixed:** the 33 inline style attributes are now classes, Metro line colours are set through
  the DOM, and the dashboard policy is `style-src 'self'` with no `'unsafe-inline'`. A static test forbids style
  attributes, a header test checks the policy, and a browser check opens 20 screens, the admin screen and the maps
  with no refusal.
- **Tests:** new `tests/browser/map_and_policy_check.py` 13/13; phase 2 18/18, real mode 14/14, screen widths 22/22,
  upcoming editor 17/17, accounts 24/24.

## Unreleased (branch `v4`): administrator accounts and account screens, 2026-11-19
- **Individual administrator accounts replace the shared key wherever accounts run.** With a permanent database and
  `ACCOUNTS_ENABLED=1`, administration uses each person's account and records it as `user:<id>`. The shared
  `ADMIN_API_KEY` then only lists accounts and assigns roles, so it can create the first administrator and nothing
  else. Without accounts (the public service today) the key works as before.
- **Staff sessions:** editors and administrators are signed out after 12 hours and on every reload (the token stays in
  the page's memory); passengers stay signed in for 30 days. Changing a role signs that account out. The last
  administrator cannot lose the role. Staff sign-ins are written to the audit log.
- **`scripts/create_admin.py`** gives an existing account a role from the server's shell (audited as `cli`).
- **Account screens:** sign in, register (one-time recovery code), recover, saved journeys in the account (with "copy
  journeys saved on this device"), notification choices (stored, nothing sent), data download, password change and
  account deletion, in all four languages. Without accounts the screen says why.
- **Administration screen:** "Accounts and roles" panel; editors see only notices and upcoming transport.
- **Tests:** pytest 544 passed, 5 skipped; new `tests/browser/accounts_check.py` 24/24. `tests/browser/serve_at.py`
  runs a local server at a chosen moment so journey checks give the same result at any hour.

## Unreleased (branch `v4`): audit and Phase 2 commuter features, 2026-11-19
- **Service notices (migration 0005).** Administrators post short notices that repeat an official source: a gov.in or
  nic.in site, bmrc.co.in, or the official BMTC or BMRCL account on X. Each needs a reason, ends within 31 days, is
  written to the audit log and can be withdrawn. Home shows the notices running today, each with its source linked,
  or says plainly that there is no live alerts feed. API: `GET /api/notices`; `GET/POST /api/admin/notices`;
  `PATCH /api/admin/notices/{id}`.
- **Journey planner.** Swap start and destination; "Use my location" fills the nearest stop or station; "Share this
  journey" gives a link (`#/journey/<from>/<to>/<modes>/<label>`) that plans the same journey when opened.
- **Quick destinations** on Home: major Metro stations, shown only if they exist in the loaded data, with its label.
- **Fixed:** "Stops near me" listed station entrances and each platform separately (near Cubbon Park, the station three
  times and five entrances). Entrances are left out and each station is listed once; a regression test fails on the
  old code.
- **Audit documents** in `docs/audit/`: AUDIT, FEATURE_GAP_ANALYSIS (against Namma BMTC 2.0), SYSTEM_ARCHITECTURE,
  SECURITY_AUDIT and IMPLEMENTATION_ROADMAP.
- **Tests:** pytest 535 passed, 5 skipped; new browser check `tests/browser/phase2_check.py` 18/18; real-mode 14/14;
  screen widths 22/22; upcoming editor 17/17; axe: no violations on 15 screens in 2 themes.

## Unreleased (branch `v4`) — PostgreSQL proven; accounts and roles built but off; data coverage audit, 2026-11-18
- **PostgreSQL.** The psycopg 3.2 driver is added, and `postgres://` and `postgresql://` addresses are accepted.
  - A CI job on PostgreSQL 16 runs the migrations twice, imports the community Metro feed twice (once only in
    effect) and runs `scripts/check_persistence.py`.
  - The persistence check: a saved route, an administrator change and a passenger account with a saved journey all
    survive a server restart.
  - A PostgreSQL-backed real-mode server passes the deployment checks.
- **Passenger accounts (migration 0004)**, built and tested but off unless `ACCOUNTS_ENABLED=1` **and** the database
  is PostgreSQL.
  - **Accounts:** registration; sign-in with bearer sessions (hashed, 30 days); lockout after eight wrong passwords;
    password change; one-time recovery codes; export; deletion.
  - **Saved data:** up to 50 saved journeys per account, and notification preferences (stored only; nothing is sent).
  - **Roles:** passenger, editor (upcoming transport) and admin. Signed-in staff are named in the audit log as
    `user:<id>`; the admin key still works.
  - **Tests:** 26.
- **Fixed.** The feature list ignored real/demo separation when deciding whether bus or Metro routes exist.
  Accounts did not recognise `postgres://` addresses.
- **Feature reasons.** Accounts are now "needs a permanent database" and notifications "needs a delivery service", in
  four languages.
- **Documents.**
  - `docs/launch/DATA_COVERAGE_REPORT.md`: what is real, unverified, missing or restricted; OpenCity datasets
    (pages refused automated access, so the owner should confirm); the community Metro audit (83 stations, valid to
    17 Aug 2027, 0 validator errors, Pink Line missing).
  - `docs/launch/POSTGRESQL_PRODUCTION.md`: recommends Render Postgres Basic-256mb in Singapore.
  - `docs/launch/ACCOUNTS_AND_ROLES.md` and `FINAL_IMPLEMENTATION_REPORT.md`.

## Unreleased (branch `v4`) — real Namma Metro data; real mode separated from demonstration mode, 2026-11-18
- **Real mode is the default.** `DEMO_MODE` is off by default, and the public service never serves the invented
  SYNTHETIC_DEMO feeds, even if one is loaded. A demonstration server sets `DEMO_MODE=1` and shows a banner on every
  screen.
  - Implementation: one per-request switch (`backend/app/demo.py`) filters imports in every timetable query and in
    the data status.
  - `render.yaml` sets `DEMO_MODE=0`, and the container seeds demo feeds only in demonstration mode.
- **Real Namma Metro data.** The community bmrcl-gtfs feed is included: Purple 37, Green 32 and Yellow 16 stations,
  valid 17 Aug 2026 – 17 Aug 2027, under ODbL, pinned by SHA-256 in `reference_data/namma_metro_community/`.
  - **Loading.** `scripts/load_community_metro.py` imports it as kind COMMUNITY, so it is always "Unverified feed".
    The Docker image already contains it, so a cold start needs no import.
  - **Planner labels.** The planner marks its times `approximate`. It never shows its fares, which the project
    estimated: fare code `NOT_VERIFIED`. Only official sources, or demo sources on a demonstration server, show fares.
  - **Station list.** Each station appears once, with its platforms merged.
  - **Not used.** The BMTC community feed (bmtc-gtfs) is built from the Namma BMTC app's data interface, so it is not
    used.
- **Fixed: a typed station name could match a different station.** "Jayanagar" matched "Vijayanagar", so the planner
  answered with a trip to Vijayanagar. Exact names now win; partial names still find every match.
  - Applies to `/api/plan` and `/api/journey`.
  - Two tests fail on the old matching and pass now.
- The live-information notice now reads: "Live vehicle information is currently unavailable. The information shown is
  scheduled data, not live tracking."
- **Tests.** `tests/test_demo_mode.py` (11), `tests/browser/real_mode_check.py` (14 checks), and CI starting a
  demonstration container and a real-mode container from one image. `scripts/verify_deployment.py` checks either
  mode.

## Unreleased (branch `v4`) — separate 4.0 deployment; editable upcoming transport, 2026-11-18
- **Render.** `render.yaml` now defines only the new service `bengaluru-transit-planner-v4` (branch `v4`, Docker,
  Singapore, health check `/api/health`), so it cannot touch the 3.0 service.
  - The container listens on `PORT` (default 8000); CI starts it on port 10000, as Render does.
  - The CI container job now asserts a 4.x version, the 4.0 page title and the upcoming entries.
  - Exact dashboard steps are in `docs/launch/DEPLOYMENT_GUIDE.md`.
  - `scripts/verify_deployment.py` proves a public address is 4.0 and that the 3.0 address is still 3.0.
- **Upcoming transport is editable without code changes.** Entries live in the database (migration 0003: tables
  `transport_announcements` and `transport_announcement_changes`). Each has a type, location and route, status,
  where the status comes from, announcement date, expected start, operating date, sources, last verification, and a
  public update history.
  - Administrators add and change entries in the Administration screen (`POST /api/admin/upcoming`,
    `PATCH /api/admin/upcoming/{id}`). Every change needs the admin key and a reason, and is audited.
  - **Types:** new bus routes, electric buses, feeders, Metro extensions, new stations, suburban rail, interchanges,
    integrated ticketing.
  - **Statuses:** Announced, Planned, Under construction, Delayed, Awaiting confirmation, Operating.
  - **Rules:**
    - "Operating" needs an opening date that is not in the future.
    - Only an official announcement may give an expected start date.
    - An estimate or demonstration entry can never be operating.
    - A verification date cannot be in the future.
  - The seven checked entries seed an empty table. Their reported target years moved into notes, because none comes
    from an official announcement.
  - Tests: `tests/test_announcements.py` (17); 12 new rule tests in `tests/test_launch.py`;
    `tests/browser/upcoming_admin_check.py`.
- **Labels.** The year banner no longer says "Official verified data for {year}" when no verified timetable
  exists. It now says "No officially verified timetable is currently available for this selection.", and likewise
  for unverified feeds.
- Service worker cache `bmtc-planner-shell-v6`, so phones fetch the new screens.

## Unreleased (branch `v4`) — government submission package, 2026-11-18
- `government_submission_2026/`: 19 documents for a technical review by Karnataka transport authorities. They cover
  the proposal, the feature matrix by area, architecture, security, privacy, accessibility, the data, licence and
  integration register, test evidence, limitations, the demonstration script, the pilot, costs, three requests, a
  cover letter and a checklist.
- Contacts verified on the official websites on 17 Nov 2026:
  - DULT contact page;
  - BMRCL project office, distinguished from passenger travel help;
  - BMTC central offices, distinguished from the complaints channel.
- The DULT Transport Data Hub address reported in the press did not resolve; the requests ask for it.
- Android workflow: a push to `v4` is now a compile check only and can never publish. The `app-v4-preview`
  pre-release needs a manual run with `publish_v4_preview` and `V4_PLANNER_URL`. `main` behaviour is unchanged.
  Guarded by `tests/test_release_guard.py` (4 tests).
- `FINAL_SUBMISSION_READINESS.md`: commit, CI, deployment, Android, data, permissions, test results, blockers and
  suitability.
- Found: the repository has no licence file, so the earlier draft letters' "open source" wording was inaccurate. The
  new package says "publicly available" until the owner chooses a licence.

## Unreleased (branch `v4`) — end-to-end functional verification, 2026-11-17

### Added
- Saved journeys on the device: "Save this journey", a Saved journeys list with Plan again and Remove, cleared by Delete my data.
- `tests/browser/e2e_check.py`: opens every screen fresh for each control, verifies each of 321 controls has an effect, then runs the full user journey, the unhappy paths, PWA installability and data-labelling checks.
- `V4_COMPLETE_FEATURE_MATRIX.md`, `V4_END_TO_END_TEST_REPORT.md`, `V4_BUGS_AND_FIXES.md`, `V4_SECURITY_REPORT.md`, `V4_DATA_VERIFICATION_REPORT.md`, `V4_RELEASE_READINESS.md`.

### Fixed
- Route pages link each stop to its stop page.
- The admin screen no longer scrolls sideways on phones (screen-reader text inside scrolled tables is now contained).
- Map credits: the OpenStreetMap credit links to its copyright page in a new tab; Leaflet is named without a link that would leave the app.
- Android shell (not yet compiled): `tel:` links (SOS, helplines) open the dialler and official sites open in the browser, where before they were silently blocked; the back button goes back a page; the app is titled Bengaluru Transit Planner.

### Tests
ruff clean; pytest 425 passed, 5 skipped; browser regression 121/121; launch 264/264; end-to-end 486/486 (321 controls, 0 decorative); axe 15 screens × 2 themes clean; security probes 34/34; bandit and pip-audit clean; load 0 errors; Android static check passed (not compiled).

## 4.0.0-beta.1 — 2026-11-17 (branch `v4`, public-demo candidate, not merged to `main`)

### Added
- Journey planner `modes` filter: bus only, Metro only, or both; mixed journeys are labelled "Bus + Metro".
- Upcoming transport registry (`/api/upcoming`) with sourced, dated statuses and a validator that rejects a future service marked as operating.
- Provider registry (`/api/providers`), feed freshness (`/api/data-status`) and the "Data and providers" screen.
- Provider integration adapters (`/api/integrations`) for live data, tickets, passes, Metro QR, payments and NCMC. Each refuses with 503 until an authorised provider exists.
- Rule-based travel assistant (`/api/assistant`, "Travel assistant" screen). It answers only through the app's own data endpoints.
- `render.yaml` for a separate 4.0 staging service; a CI container job; CI on pushes to `v4`.
- `LAUNCH_READINESS.md` and `docs/launch/` (feature matrix, sources, integrations, security, privacy and accessibility, test results, deployment, limitations, release notes, demo guide).
- `tests/test_launch.py` (43 tests) and `tests/browser/launch_check.py` (264 browser checks).

### Fixed
- Security probe for keyless saved-route reads now matches documented behaviour (finding S6).

### Tests
ruff clean; pytest 425 passed, 5 skipped; browser regression 121/121; launch browser checks 264/264; axe 15 screens × 2 themes clean; security probes 34/34; bandit and pip-audit clean; load test 0 errors.

## 4.0.0-alpha.3 — 2026-11-16 (branch `v4`, not released)

Government-readiness audit: fixes found by testing, and the evaluation documents.

### Fixed
- **Accessibility:** scrollable tables could not be reached by keyboard (axe `scrollable-region-focusable`, serious). All 8 tables are now focusable regions with their own labels.
- **Privacy:** the container no longer writes uvicorn's access log, which recorded search text and "stops near me" coordinates with the visitor's IP address.
- **Privacy:** new `DELETE /api/my-data` and a "Delete my data" control (My account, with an on-page confirmation). It erases everything the server holds for the device and clears the device's own lists; its audit entry stores only counts.
- **Security:** HSTS (`max-age=31536000`) on HTTPS responses; the live site sent none.

### Added
- `docs/government/`: readiness audit, security audit, production-readiness report, accessibility audit, privacy policy, terms, retention policy, data and services registers, contact strategy, pilot proposal, submission status, and draft letters to BMTC, BMRCL and DULT (not sent).
- `tests/audit/`: the accessibility, security-probe and load-test scripts behind the audit.

### Tests
ruff clean; pytest 382 passed, 5 skipped; browser checks 121/121; axe 10 screens × 2 themes clean; security probes 32/33 (1 probe expectation corrected); pip-audit and bandit clean; load test 0 errors.

## 4.0.0-alpha.2 — 2026-11-16 (branch `v4`, not released)

Phase 2: bus and stop features, Metro stations, and bus + Metro journeys.

### Added
- `GET /api/stops/{id}/routes`: every route calling at a stop, with the places it runs towards.
- `GET /api/metro/stations`: stations served by Metro routes (GTFS `route_type` 1 and urban-rail types), with their lines and colours, and a name search.
- Journey legs now carry `mode` (bus, metro, rail, tram, other) and `route_type`; the app shows a Bus or Metro tag on every ride.
- Stop page: routes at this stop, walking directions (OpenStreetMap), Save stop.
- Favourites: saved stops next to saved routes (stops are kept on the device only).
- Recent searches on Home (device only, with Clear).
- Empty searches say when the other data classification has matches and offer to switch; the two are never mixed.
- Namma Metro page: station directory with search.
- A SYNTHETIC demo Metro line (`build_synthetic_metro_feed`), seeded on Render next to the demo buses, so bus + Metro planning can be tried. It is invented and labelled as such.
- 27 new interface entries in each of the four languages.

### Tests
ruff clean; pytest 378 passed, 5 skipped; browser checks 121/121; 19 Edge workflow checks; pip-audit: no known vulnerabilities.

## 4.0.0-alpha.1 — 2026-11-16 (branch `v4`, not released)

Phase 1 of Bengaluru Transit Planner 4.0: one mobile-first app shell. All 3.0 features are kept.

### Added
- **New name:** Bengaluru Transit Planner (web page, manifest, API title and `/api/meta`). The unofficial notice now also names Chalo and the Government of Karnataka.
- **Opening screen:** original artwork (a generic Bengaluru skyline, a Metro viaduct and a city bus), the app name and the unofficial notice. It hides when the app is ready, and on its own after 4 seconds if the app cannot start.
- **Home screen:** route/stop search that hands the query to Routes or Stops, a Bengaluru map card with "Stops near me", and ten tiles, each showing the feature's real status.
- **Navigation:** a menu with the nine sections (Home, Nearby stops, Plan a journey, Live tracking, Tickets and passes, Namma Metro, Favourites, My account, More services) and the 3.0 planner tools; a bottom bar on phones.
- **Honest sections:** Live tracking and Tickets and passes say plainly that they are not available and why, and point to official channels. Namma Metro lists Metro lines when a Metro feed (GTFS `route_type` 1) is loaded, and says so when none is.
- **Settings (My account):** light, dark or device theme; low-data mode (the home map loads only on tap; on by default when the browser asks to save data); larger text and buttons. Saved on the device only.
- **More services:** an SOS card that opens the phone dialler for 112 (the app sends no alerts itself), official websites and helplines checked on 16 November 2026, the 3.0 tools, and an app-status list of every feature.
- **API:** `GET /api/features` (each feature's state: AVAILABLE, NO_DATA, UNAVAILABLE or PLANNED, with a reason) and `GET /api/services` (official links and helplines; kept for offline reading).
- **Translations:** 114 new entries in each of English, Kannada, Telugu and Hindi (first drafts for review; see `docs/4.0/TRANSLATION_REVIEW_CHECKLIST.md`).
- **Android workflow:** builds a separate 4.0 preview APK from `v4` once the variable `V4_PLANNER_URL` names a deployed 4.0 site; it is published as the `app-v4-preview` pre-release and never replaces the stable APK.

### Changed
- The default page is Home instead of Routes. The year-status panel appears only on the planner tools.
- Version 4.0.0-alpha.1 in `/api/meta` and the OpenAPI document; service-worker cache `bmtc-planner-shell-v4`.

### Not included yet
Live tracking, tickets, passes, payments and NCMC card services stay unavailable (no authorised provider). Accounts, notifications, facilities and the AI assistant are planned for later phases.

## 3.0.0 — 2026-11-16

Built on 2.0.0. The direct journeys, scenarios, audit log, nearby stops, backups and saved routes were already in 2.0. The changes to them are listed below.

### Added

- **Journeys with up to two changes.** `GET /api/plan` searches the feeds of one classification. It returns up to five options by default (`limit`, 1 to 10), ordered by arrival time and then by number of changes. The earliest-arrival and fewest-changes options carry the labels `EARLIEST_ARRIVAL` and `FEWEST_CHANGES`. Each answer names the transfer assumptions it used: a minimum change time (3 minutes by default), a longest walk between stops (300 metres) and a walking speed (4.8 km/h). Walks are marked as estimates, and every ride names its feed. Live positions are never shown.
- **Fares from GTFS.** `fare_attributes.txt` and `fare_rules.txt` are imported. Migration `0002_fares` adds their two tables. A one-ride journey shows a fare only when exactly one fare applies to its route. Several fares, or none, are reported without a total. Journeys with changes get no total, because transfer rules are not applied. Fares that depend on origin, destination or zone are not used.
- **Saved copies for offline reading.** The service worker keeps up to 120 saved API answers in its timetable cache, and drops the oldest first. They cover the list of routes, one route, its timetable, the list of stops and the list of data sources. A kept answer served while offline carries `X-Served-From-Cache: 1` and the time it was saved in `X-Saved-At`. A request with typed search words is never kept.
- **Telugu.** The dashboard has a Telugu translation, a first draft that no native speaker has reviewed. Each language has 344 keys. In 2.0, English, Kannada and Hindi had 309 keys each, and there was no Telugu. Version 3.0 adds 41 keys and removes 6.
- **Affiliation notice.** The footer and `/api/meta` state that the planner is not affiliated with, endorsed by or authorised by BMTC, BMRCL, Namma Metro or any transport operator.
- **Security and verification material.** `docs/SECURITY_ASVS.md` maps the planner to OWASP ASVS 5.0.0 and the OWASP Top 10:2025. The mapping is partial and self-assessed, and the gaps are stated. New tests cover the plan API, the planner, fares, planner performance, the OpenAPI document and the security headers. A planner benchmark (`scripts/bench_planner.py`) and a second mutation harness for the planner (`tests/mutation/planner_mutation_check.py`) were added.
- **Accessibility engine.** axe-core 4.14.0 is vendored in `tests/browser/vendor/axe-core/`. The browser checks use it to test WCAG 2.1 AA on the main views.
- **Banner.** `assets/banner.svg`.

### Changed

- The version is 3.0.0 in the API (`/api/meta`) and in the OpenAPI document. It was 2.0.0.
- The service worker cache is `bmtc-planner-shell-v3`. It was `bmtc-planner-shell-v2`. Caches from older versions are deleted when the new worker activates.
- The upload endpoint's OpenAPI entry documents the 422 response for a rejected feed. The status codes are unchanged: 201 for a completed import and 422 for a rejected one.
- The import report includes the number of fares.
- The web app manifest no longer describes the timetables as coming from official feeds.
- `requirements-dev.txt` lists `freezegun`, which `tests/test_plan_api.py` imports. `requirements-verified.txt` lists `freezegun` and `python-dateutil`, which it needs. `setup_windows.bat` installs `requirements-dev.txt`, so Windows setup includes `freezegun` too.
- The documentation was brought into line with the code. `docs/PRIVACY.md` and `docs/TRANSLATION.md` were rewritten. `docs/architecture.md`, `docs/API.md` and `docs/DEPLOY.md` were corrected.

### Not included

- **No Namma Metro data.** No metro feed is shipped or tested. The planner stores each feed's route type and returns it with the route data, but journeys ignore it.
- **No live positions.** No verified real-time feed is connected, so no live bus positions or delays are shown.
- **No official BMTC data.** No BMTC timetable is loaded. The official candidate, the DULT Transport Data Hub, could not be reached from the build sandbox, and its licence is unknown.
- **Draft translations.** The Kannada, Telugu and Hindi text has not been reviewed by native speakers. Right-to-left languages have not been tested.
- **Deployment kit not run.** The Docker image and the Caddy configuration were not built or run. The build sandbox has no Docker daemon.
- **No production-readiness claim.** Real-world integration and deployment testing have not been done.
