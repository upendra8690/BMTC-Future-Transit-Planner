# Test results — 4.0.0-beta.1 (run on 17 November 2026)

Machine: Windows 11, Python virtual environment, Microsoft Edge through Playwright. The demo server used the
SYNTHETIC demo feeds only.

| # | Command | Result |
|---|---|---|
| 1 | `python -m ruff check .` | All checks passed |
| 2 | `python -m pytest -p no:cacheprovider` | **425 passed, 5 skipped**, 0 failed |
| 3 | `python tests/browser/run_browser_checks.py --chrome <msedge.exe>` (existing 3.0 + 4.0 regression) | **121 passed, 0 failed** |
| 4 | `python tests/browser/launch_check.py http://127.0.0.1:8020/` (new) | **264/264 passed** |
| 5 | `python tests/audit/audit_a11y.py tests/browser/vendor/axe-core/axe.min.js` | **No violations on 15 screens × 2 themes** |
| 6 | `python tests/audit/security_probes.py <keyfile>` | **34 passed, 0 failed** |
| 7 | `python -m bandit -r backend/app` | No issues identified |
| 8 | `python -m pip_audit -r requirements.txt` | No known vulnerabilities found |
| 9 | `python tests/audit/load_audit.py` | 1 user: 90 requests, 0 errors. 20 concurrent users: 900 requests, 0 errors; slowest p95 150 ms (departures) |

## Skipped tests (5)
All five need the DejaVu Sans font for Kannada and Telugu text in PDF exports. The font is not installed on this
machine. They are skipped, not failed: `test_config.py:67`, `test_exports_and_pdf.py:166, 175, 182, 222`.

## New tests in this release (`tests/test_launch.py`, 43 tests)
| Scenario | Tests |
|---|---|
| Bus-only journey | Rides are all buses; every option is labelled `["bus"]` |
| Metro-only journey | Rides are all Metro |
| Bus + Metro interchange | Mixed options carry `BUS_AND_METRO`; the bus and Metro filters never return the other mode |
| No available route | Unknown origin gives `ORIGIN_NOT_FOUND`; Metro-only between bus stops gives `NO_JOURNEY_FOR_MODE`; unknown mode gives 422 |
| Stale data | A feed that ended in 2020 is reported `EXPIRED`; a current feed `CURRENT` |
| Missing live feed | `realtime: false`, `live_feed: NONE`, live tracking `UNAVAILABLE`, live request refused with 503, every ride `scheduled` |
| Invalid ticket integration | Bus tickets, passes, Metro QR: 503 with code; no ticket, QR or receipt fields; unknown capability 404; malformed 422 |
| Payment provider unavailable | Payments and NCMC: 503 with code; no payment or balance fields |
| Unauthorised account access | Device B cannot read device A's routes, and B's "Delete my data" erases nothing of A's |
| Future service marked as operating | Validator rejects: operating without an opening date, an opening date in the future or after the check date, a non-operating entry with an opening date, an unknown status, a missing or non-HTTPS source, a missing check date |
| Provider registry | Every row has licence, permission, owner, frequency, integration, limitations and last update |
| Travel assistant | 15 question-to-intent cases; the endpoint returns only an intent and parameters, never its own answer |

Offline mode is covered by the existing browser checks (the browser is set offline, and saved items are read from
the service-worker copy).

## Tests changed, not weakened
- `tests/test_dashboard_static.py`: added the new message code `NO_JOURNEY_FOR_MODE` and the new translation prefixes
  to the lists the test checks.
- `tests/test_now_api.py`, `tests/test_plan_api.py`: version pin `4.0.0-alpha.3` → `4.0.0-beta.1`.
- `tests/audit/security_probes.py`: the keyless saved-routes probe now checks that a keyless **write** is refused (400)
  and a keyless **read** discloses nothing. This matches finding S6, which the earlier audit recorded as corrected
  but the script still expected 400 for the read.

## Not tested
- A real Android phone, or the 4.0 APK (not built).
- The public HTTPS deployment (not created yet).
- The Docker image on this machine (Docker is not installed). A CI job that builds and calls the image was added and
  runs on GitHub.
- A real screen reader.
