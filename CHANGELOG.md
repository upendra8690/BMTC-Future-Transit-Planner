# Changelog

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
