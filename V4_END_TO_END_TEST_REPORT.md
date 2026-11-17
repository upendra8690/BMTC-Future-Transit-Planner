# V4 end-to-end test report — 17 November 2026

Machine: Windows 11, project virtual environment, Microsoft Edge through Playwright. Servers ran locally with fresh
SQLite databases seeded by `scripts/seed_demo_feed.py` (synthetic demo data only). For the browser suites the
per-minute rate limit was raised, because the scripts send hundreds of requests a minute; the limit itself is tested by
pytest and was seen working (HTTP 429) during this work.

## Results of every suite (final run, after all fixes)
| # | Suite | Exact command | Result |
|---|---|---|---|
| 1 | Lint | `python -m ruff check .` | All checks passed |
| 2 | Unit, API, integration, migrations, static front-end | `python -m pytest -p no:cacheprovider` | **425 passed, 5 skipped, 0 failed** |
| 3 | Browser regression (3.0 + 4.0) | `python tests/browser/run_browser_checks.py --chrome "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"` | **121 passed, 0 failed**; other browser problems: 0 |
| 4 | Launch screens, 4 languages, phone + desktop | `python tests/browser/launch_check.py http://127.0.0.1:8020/` | **264/264** |
| 5 | End-to-end crawl, forms, user journey, PWA, labels | `python tests/browser/e2e_check.py http://127.0.0.1:8040/ <admin-key-file> <report.json>` | **486/486**; 321 controls exercised, **0 decorative or broken** |
| 6 | Accessibility (axe-core, WCAG 2.1 A/AA + best practice) | `python tests/audit/audit_a11y.py tests/browser/vendor/axe-core/axe.min.js` | **No violations on 15 screens × 2 themes** |
| 7 | Security probes | `python tests/audit/security_probes.py <admin-key-file>` | **34 passed, 0 failed** |
| 8 | Static security analysis | `python -m bandit -r backend/app` | No issues identified |
| 9 | Dependency vulnerabilities | `python -m pip_audit -r requirements.txt` | No known vulnerabilities found |
| 10 | Load | `python tests/audit/load_audit.py` | 1 user: 90 requests, 0 errors, p95 47 ms. 20 concurrent users: 900 requests, 0 errors |
| 11 | Android shell (static only) | `python android/check_starter.py` (separate venv with `requirements-android-check.txt`) | YAML ok; Dart grammar 0 errors; 10/10 required behaviours present. **Not compiled** |
| 12 | Outside links | Fetched each of the 18 unique URLs the app shows, then retried failures in Edge | 18/18 open with status 200 in a browser |

Skipped (5): PDF tests that need the DejaVu Sans font, which is not installed here (`test_config.py:67`,
`test_exports_and_pdf.py:166, 175, 182, 222`).

**Not run:** GitHub CI for the last push (the GitHub API was unreachable from this machine; check the Actions tab),
the Docker image (no Docker here; CI builds it), the Android build, any real phone, a real screen reader.

## The user journey from the brief (phone size, 390 × 844)
| Step | Check | Result |
|---|---|---|
| 1 | The app opens on the home screen | PASS |
| 2–3 | Bus-only journey Demo Central → Demo Junction; every ride is a bus; each ride labelled Unverified feed; says not live | PASS |
| 4 | Route DEMO-1: stops listed, timetable loads, a stop opens from the route page | PASS (stop links added this round) |
| 5 | Metro-only journey; every ride is Metro | PASS |
| 6 | Bus + Metro journey with a walk between bus stop and station | PASS |
| 7 | Save this journey → stored with mode and classification → listed in Favourites → Plan again re-plans it; a saved route is stored on the server | PASS (saved journeys built this round) |
| 8 | Switch to Kannada: navigation translated, `lang="kn"` | PASS |
| 9 | Refresh: still Kannada; saved journey and route still listed | PASS |
| 10 | Offline: app shell loads; saved journeys readable; planning shows an error with Retry; offline banner shown | PASS |
| 11 | Journey screen fits 390 px (all 18 screens checked in the crawl) | PASS |

## Unhappy paths
| Scenario | Result |
|---|---|
| Unknown origin | "No stop matches" message — PASS |
| Metro only between two bus stops | "No journey using only the chosen mode" — PASS |
| Officially verified data chosen (none exists) | Says no official timetable is available — PASS |
| Server error (HTTP 500) | Message and Retry button — PASS |
| Dropped connection | Message — PASS |
| One-letter or empty journey fields | Refused before any request — PASS |
| Empty or 300-character assistant question | Refused / cut to 200 — PASS |
| Live arrival question | Assistant refuses to invent it — PASS |
| Ticket, Metro QR, payment request | 503, no ticket, QR or payment fields — PASS |
| Location refused | "Location permission was not given. Search by stop name instead."; no location sent — PASS |
| Wrong admin key | Refused with a message, no data shown — PASS |

## How "no decorative buttons" was proved
`e2e_check.py` opens each screen fresh for every control, uses the control once, and compares the page before and
after: the route, the screen content, messages, dialogs, display settings, device storage, API requests and
downloads. 321 controls on 20 screens all produced an effect. Form choices (journey changes and travel mode) were
checked by confirming the values reach the server (`max_changes=0`, `modes=bus`). Map zoom buttons were checked by
confirming the map moved. Destructive actions (Delete my data, removing an import) were tested in their own steps.
