# Phase reports

Each phase records what was actually built and tested, what is still unavailable and why, and the real test results.

## Phase 1 — Mobile-first app shell (4.0.0-alpha.1, 16 November 2026)

### Implemented and tested
| Feature | How it was verified |
|---|---|
| New name "Bengaluru Transit Planner" (page, manifest, API) with the unofficial notice | `tests/test_features_api.py`; browser check on the site notice |
| Opening screen (original artwork, hides when ready, self-hides after 4 s) | Edge run: shown at start, hidden after load, on phone and desktop |
| Home: search handed to Routes/Stops, Bengaluru map card, 10 status tiles | Edge run: "DEMO-2" typed on Home appears in the Routes search box |
| Menu with 9 sections + 3.0 tools; bottom bar on phones | `test_every_menu_link_leads_to_a_page_the_app_can_show`; Edge run of all 15 pages with no JavaScript errors |
| `/api/features` with states worked out from loaded data | 7 tests, including Metro detected by `route_type` 1 and a deleted feed no longer counting |
| Unauthorised features never reported as available | `test_unauthorised_capabilities_are_never_reported_as_available` |
| `/api/services`: official HTTPS sites (each opened and title-checked) and digit-only phone numbers | 2 tests; 7 of 8 candidate links verified live, IRCTC left out because it could not be checked |
| Live tracking / Tickets / NCMC: clear unavailable screens with reasons and official channels | Edge run and screenshots |
| Namma Metro section: lists Metro lines from a Metro feed; says when none is loaded | Edge run (no Metro feed: "No data yet"); feature test for detection |
| Theme (device/light/dark), low-data mode, larger text, saved on the device | Edge run: dark + large text survive a reload; low-data holds the map until tapped |
| SOS card opening the phone dialler for 112 | Screenshot; the app claims no alert delivery |
| 114 new interface entries in each of 4 languages | Static tests: same keys in every language, placeholders kept, no untranslated English, every key used |
| Offline: official links kept for offline reading; `/api/features` never cached | Static service-worker test extended |

### Not available, and why
| Feature | Reason |
|---|---|
| Live bus tracking | No authorised BMTC live feed |
| Bus tickets, passes, Metro QR tickets, payments | No agreement with BMTC/BMRCL/ONDC and no payment gateway |
| NCMC card services | Issued and recharged by banks; needs bank integration |
| Real Bengaluru routes | The official DULT feed has not been downloaded yet (owner action) |
| Accounts, notifications, facilities, AI assistant | Planned for later phases |

### Tests run
| Check | Result |
|---|---|
| `ruff check .` | All checks passed |
| `pytest` (Windows, Python 3.12) | 371 passed, 5 skipped (DejaVu Sans font not installed) |
| Browser checks `tests/browser/run_browser_checks.py` (Edge, headless) | 121 passed, 0 failed |
| Phase 1 Edge run of every page, phone and desktop | No JavaScript errors; 429 responses appeared only when the script loaded 30+ pages in a minute (the rate limit working) |

### Android
A 4.0 preview APK is configured but **not built**: it would only show the website it points at, and no 4.0 site is
deployed yet. It builds automatically once the repository variable `V4_PLANNER_URL` is set to a deployed 4.0 site.

### Known issues
- Home search uses the selected classification (default "Official verified"). With no official feed loaded, it finds
  nothing until the user switches to "Unverified feed". Honest, but easy to miss; to revisit in Phase 2.
- Kannada, Telugu and Hindi text is unreviewed (checklist added).

## Phase 2 — Bus, stops, Metro stations, bus + Metro journeys (4.0.0-alpha.2, 16 November 2026)

### Implemented and tested
| Feature | How it was verified |
|---|---|
| Routes at a stop with directions | API tests (DEMO-1 and DEMO-2 at Demo Market; classification enforced; unknown stop 404) |
| Metro station directory with search | API tests (4 demo stations, line colour, name filter, "no stations" message without a Metro feed) |
| Bus + Metro journey with a mode on every ride | API test: Demo Lake View to Demo Metro Hub uses a bus, a 55 m walk and the Metro, each ride naming its feed |
| Bus-only rides labelled bus | API test |
| Bus + Metro journeys AVAILABLE only when both feeds are loaded | API test |
| Empty search offers the other classification | Edge workflow |
| Walking directions, save/reopen favourite stop, recent searches | Edge workflow |
| Metro page in Hindi, Telugu, Kannada | Edge workflow |

### Tests run
| Check | Result |
|---|---|
| `ruff check .` | All checks passed |
| `pytest` | 378 passed, 5 skipped |
| Browser checks (Edge) | 121 passed, 0 failed |
| Phase 2 Edge workflows (19 checks) | 19 passed, no JavaScript errors |
| `pip-audit -r requirements.txt` | No known vulnerabilities found |

### Not available, and why
Real BMTC/Metro data (DULT feed not yet downloaded); bus categories (no source data); live tracking, tickets and
payments (provider approval); accounts (Neon credentials). See the status table in `FEATURE_MATRIX_4_0.md`.
