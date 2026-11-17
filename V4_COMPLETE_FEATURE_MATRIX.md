# V4 complete feature matrix — 17 November 2026 (branch `v4`, 4.0.0-beta.1)

Statuses: **PASS** implemented and tested · **PARTIAL** some functionality works · **DEMO ONLY** works, but only on
the synthetic demonstration data · **BLOCKED** depends on an integration, permission or environment we do not have
· **FAIL** tested and broken · **NOT IMPLEMENTED** missing.

There is no licensed BMTC or BMRCL data, so every timetable-based feature is **DEMO ONLY**. Evidence names refer to
the suites in [V4_END_TO_END_TEST_REPORT.md](V4_END_TO_END_TEST_REPORT.md): `pytest`, `regression` (121 browser
checks), `launch` (264), `e2e` (486), `axe`, `probes` (34).

## Screens and navigation
| Item | Status | Evidence |
|---|---|---|
| 18 screens (Home, Nearby, Plan, Live, Tickets, Metro, Favourites, My account, More, Upcoming, Assistant, Data and providers, Routes, Stops, Scenarios, Compare, Data sources, Admin), plus route and stop pages | PASS | e2e: each renders at 390 px and 1280 px, no error banner, no horizontal scroll |
| Sidebar, bottom navigation, menu on phone | PASS | regression; e2e link checks (117 in-app links all open a screen) |
| Every button, choice and switch (321 controls) | PASS | e2e crawl: 0 decorative, 0 broken |
| Every in-app link (117) | PASS | e2e |
| Every external link (18 unique) | PASS | e2e (https, new tab, `noopener`); all 18 open with status 200 in a real browser |
| Phone links (112, 108, 101, 1098, 139) | PASS | e2e: valid `tel:` links |

## Transport features
| Feature | Status | Notes |
|---|---|---|
| Bus route search (number, name) | DEMO ONLY | e2e forms: results and no-match message |
| Bus stop search (name) | DEMO ONLY | e2e forms |
| Route details, stop sequence, links to each stop | DEMO ONLY | Stop names now link to the stop page (fixed this round) |
| Bus timetables, first and last trips | DEMO ONLY | regression: 66 trips on 1 Jan 2027; CSV download |
| Fare information | DEMO ONLY | Only from fare rules in the loaded feed; the demo fares are invented |
| Direct and interchange journeys (up to 2 changes) | DEMO ONLY | e2e: changes=0 is sent and respected |
| Nearby stops (location on tap) | DEMO ONLY | regression (location given); e2e (location refused: clear message, nothing sent) |
| Map display | DEMO ONLY | OpenStreetMap tiles need internet; zoom controls verified in e2e |
| Metro lines, stations, station search | DEMO ONLY | e2e forms |
| Bus only / Metro only / bus + Metro journeys | DEMO ONLY | pytest (6 tests) and e2e journey steps 3, 5, 6 |
| Walking connections | DEMO ONLY | e2e step 6: walk leg between bus stop and station |
| Upcoming transport with statuses | PASS | 7 projects, sources and dates; validator tests; all source links open |
| Service alerts | NOT IMPLEMENTED | No authorised alerts feed exists to show; no alerts screen |
| Saved routes (server, per device) | PASS | e2e: stored on the server under the device key; listed after refresh |
| Saved stops (device) | PASS | regression |
| Saved journeys (device) | PASS | **New this round.** e2e step 7: save, list, Plan again; kept after refresh; readable offline |
| Airport connections | PARTIAL | Official airport website link works; Vayu Vajra timetables are BLOCKED (no BMTC data) |
| Passenger facilities | PARTIAL | Emergency numbers and official links work; hospitals, toilets, parking and so on are NOT IMPLEMENTED (no licensed dataset) |
| Live tracking and ETA | BLOCKED | No authorised feed; screen explains; adapter refuses with 503 |
| Bus tickets, passes, Metro QR, payments, wallet, NCMC | BLOCKED | Adapters refuse with 503; no ticket, QR, receipt or payment is ever produced (pytest, e2e) |
| Language switching (en, kn, te, hi) | PASS | e2e step 8 and refresh step 9; key parity enforced by pytest. Translations not professionally reviewed |
| Travel assistant | DEMO ONLY | Rule-based, not AI; English questions only; answers come from the app's data endpoints; refuses live, ticket and payment questions |
| Future scenarios 2027–2030 (3.0 feature) | PASS | regression; labelled estimates |

## Accounts, security, privacy
| Feature | Status | Notes |
|---|---|---|
| User accounts (registration, login, profile) | NOT IMPLEMENTED | Planned with Neon Postgres |
| Device data isolation | PASS | pytest; probes |
| Delete my data | PASS | e2e: server rows removed, device lists cleared, new device key |
| Admin sign-in and data management | PASS | regression; e2e crawl with the key; wrong key refused |
| Notifications | NOT IMPLEMENTED | |

## Mobile, offline, Android
| Feature | Status | Notes |
|---|---|---|
| Mobile layout | PASS | e2e: every screen at 390 px with no horizontal scroll (admin was failing; fixed this round) |
| PWA installability | PASS | Chromium's own installability check reports no errors (e2e). Not installed on a real phone |
| Offline: app shell and saved information | PASS | e2e step 10; regression offline checks |
| Offline: planning a new journey | PASS (correctly unavailable) | Shows an error with a retry button, not a blank page |
| Low-data mode, dark mode, large text | PASS | e2e crawl: each switch changes the display |
| Accessibility (automated WCAG 2.1 AA) | PASS | axe: 15 screens × 2 themes, no violations. No real screen-reader test |
| Android app (WebView shell) | BLOCKED | Not compiled here (no Flutter SDK). The v4 APK build waits for `V4_PLANNER_URL`. Not run on a phone |
| Android: official-site and phone links, back button | PARTIAL | **Defect found by code review** (links, including SOS, were silently blocked; no back handling). Fixed in code and passes the Dart syntax check; not yet compiled |
| Android: location for "Stops near me" | NOT IMPLEMENTED | The WebView does not ask for location; the page falls back to search by name |
