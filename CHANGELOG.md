# Changelog

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
