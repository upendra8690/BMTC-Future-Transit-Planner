# V4 bugs and fixes — 17 November 2026

## Bugs in the app, found and fixed this round
| # | Found by | Problem | Fix | Verified by |
|---|---|---|---|---|
| 1 | e2e user journey (step 7) | **Saving a favourite journey did not exist**, although the brief's journey needs it | Saved journeys on the device: "Save this journey" under results, a "Saved journeys" list in Favourites with Plan again and Remove; cleared by Delete my data; four languages | e2e step 7, refresh step 9, offline step 10, privacy checks |
| 2 | e2e user journey (step 4) | The route page listed stop names as plain text; a rider could not open a stop from a route | Each stop name links to its stop page | e2e step 4 |
| 3 | e2e layout check | **Admin screen was 76 px wider than a phone** (horizontal page scroll). Cause: screen-reader-only text inside a scrolled table escaped the table's clipping | `.table-wrap { position: relative; }` | e2e: all 18 screens at 390 px; axe |
| 4 | e2e link check | The map's "Leaflet" credit opened leafletjs.com in the same tab, which in the installed app would leave the app; the OpenStreetMap credit had no link to its copyright page | OSM credit links to openstreetmap.org/copyright in a new tab; Leaflet named without a link | e2e; pytest external-hosts test unchanged |
| 5 | Code review of the Android shell | **The Android app silently blocked every link outside the planner's host, including `tel:` links — so SOS "Call 112", helplines and official-site buttons did nothing in the APK.** No back-button handling; old app name | `url_launcher` opens `tel:` in the dialler and `https` in the browser; back button goes back a page; title "Bengaluru Transit Planner" | Dart syntax check (10/10 required behaviours). **Not compiled or run on a phone yet** |
| 6 | pytest (during this work) | A translation key built at run time (`journey.modes_` + mode) | Explicit key table | pytest static checks |

Bugs 1–4 and 6 are on the web app and fully retested. Bug 5 still needs a build and a phone test (see
[V4_RELEASE_READINESS.md](V4_RELEASE_READINESS.md)). Bug 5 also affects the **3.0 APK on `main`** (`app-latest`),
which has the same shell. `main` was not changed, because changes to 3.0 need your approval.

## Test-method corrections (the checker was wrong, not the app)
| Checker problem | Correction |
|---|---|
| Journey form choices (changes, mode) were flagged as "no effect" because they only matter when the form is sent | They are now verified by checking that the chosen values reach the server |
| Map zoom buttons (`href="#"`, part of Leaflet) were treated as external links | They are now verified by checking that the map zooms |
| The wrong-admin-key message was looked for on the page; the app shows it as a message toast | The check now reads the toast and confirms no admin data is shown |
| PWA installability reported `in-incognito` | Test browsers are private by default; the check now uses a normal browser profile |

No test was removed or weakened. Two lists in `tests/test_dashboard_static.py` were extended for the new feature:
the allowed device-storage keys (`favJourneys`) and a line wrap. The crawler `tests/browser/e2e_check.py` has one
lint exception for long lines, like the existing audit scripts.

## Earlier in 4.0.0-beta.1 (commit 126a381)
- The security probe for keyless saved-route reads expected 400 for a read; it now checks that a keyless write is
  refused and a keyless read discloses nothing (finding S6).

## Known problems not fixed (need permission, data or hardware)
See the "Five most important remaining problems" in [V4_RELEASE_READINESS.md](V4_RELEASE_READINESS.md).
