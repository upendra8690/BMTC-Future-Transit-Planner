# Government readiness audit

Audit date: 16 November 2026. Code: branch `v4` (4.0.0-alpha.3). Environment: Windows 11, Python 3.12,
Microsoft Edge (headless) for browser tests; the app was run locally with the SYNTHETIC demo bus and Metro feeds.

## Method
1. Repository inspection: `main` (3.0, live) and `v4` (4.0) branches, commits, CI history, docs.
2. Automated tests: `pytest` (backend and static frontend rules), 121 browser checks, Phase 2 workflow checks.
3. New checks written for this audit (`tests/audit/`): axe-core accessibility scan of every 4.0 screen, 33 security
   probes against a running server (including stored XSS in a real browser), and a concurrent load test.
4. Dependency scans: `pip-audit` and `bandit`.
5. Live site check: response headers of the public 3.0 site.

## Results in brief
| Check | Result |
|---|---|
| `ruff` lint | Clean |
| `pytest` | 382 passed, 5 skipped (DejaVu font not installed on this PC) |
| Browser checks (3.0 behaviour incl. WCAG scans of 3.0 views) | 121 / 121 |
| Phase 2 user workflows in Edge | 19 / 19 |
| Delete-my-data workflow in Edge | 4 / 4 |
| axe-core WCAG 2.1 AA on 10 screens × light/dark | 1 serious issue found, fixed, rescan clean |
| Security probes | 32 / 33 pass; the 1 "failure" was a wrong expectation in the probe (see security audit S6) |
| `pip-audit -r requirements.txt` | No known vulnerabilities |
| `bandit -r backend scripts` | No issues reported |
| Load test, 20 concurrent users, 900 requests | 0 errors; p50 21 ms, p95 105 ms (demo-sized data) |

## Feature classification
Labels: WORKING AND VERIFIED · WORKING WITH DEMO DATA · WORKING WITH AUTHORISED DATA · INCOMPLETE ·
BLOCKED BY PROVIDER APPROVAL · SECURITY ISSUE · NOT IMPLEMENTED.
**No feature is WORKING WITH AUTHORISED DATA**, because no official BMTC or BMRCL feed has been obtained.

| # | Feature | Classification | Evidence |
|---|---|---|---|
| 1 | Bus route search | WORKING WITH DEMO DATA | API tests; Edge workflow |
| 2 | Bus stop search | WORKING WITH DEMO DATA | API tests; Edge workflow |
| 3 | Routes serving each stop | WORKING WITH DEMO DATA | `test_phase2_api.py`; Edge workflow |
| 4 | First and last service times | WORKING WITH DEMO DATA | Timetable summary tests (first departure, last arrival per date) |
| 5 | Timetables (route, stop departures, CSV) | WORKING WITH DEMO DATA | 3.0 timetable tests; browser checks |
| 6 | Fare calculation | INCOMPLETE | One-ride GTFS fares tested; no real fare data; multi-leg totals not applied |
| 7 | Bus journey planning (≤2 changes) | WORKING WITH DEMO DATA | Planner, API and mutation tests |
| 8 | Bus + Metro journeys | WORKING WITH DEMO DATA | API test and Edge workflow with the synthetic Metro line |
| 9 | Nearby stops | WORKING WITH DEMO DATA | 3.0 tests; location requested only on tap |
| 10 | Walking directions | WORKING AND VERIFIED | Link to OpenStreetMap directions, checked in Edge |
| 11 | Metro station search | WORKING WITH DEMO DATA | API tests; Edge workflow |
| 12 | Metro line information | WORKING WITH DEMO DATA | Edge workflow |
| 13 | Favourite routes and stops | WORKING AND VERIFIED | Device-scoped; isolation probe; Edge save/reopen |
| 14 | Saved journeys | NOT IMPLEMENTED | Needs accounts (Neon) |
| 15 | English, Kannada, Telugu, Hindi | WORKING AND VERIFIED (text unreviewed) | Static parity tests; Edge in each language; native-speaker review pending |
| 16 | Offline (saved timetables, links) | WORKING AND VERIFIED | Service-worker tests; browser offline checks |
| 17 | Android navigation | INCOMPLETE | APK builds in CI; back-button handling, location bridge and offline screen not built; not device-tested here |
| 18 | Location permission handling | WORKING AND VERIFIED (browser) | Denied/unsupported paths tested in browser checks; Android bridge pending |
| 19 | Low-data mode | WORKING AND VERIFIED | Edge: map waits for tap |
| 20 | Accessibility | WORKING AND VERIFIED | axe clean on 10 screens × 2 themes; 3.0 scans in browser checks |
| 21 | Delete my data | WORKING AND VERIFIED | API tests; Edge workflow |
| 22 | Future scenarios 2027–2030 (labelled estimates) | WORKING AND VERIFIED | 3.0 tests |
| 23 | GTFS import, validation, verification, audit log | WORKING AND VERIFIED | 3.0 tests; ZIP-bomb and non-ZIP probes |
| 24 | Live bus tracking / live ETA | BLOCKED BY PROVIDER APPROVAL | No authorised feed |
| 25 | Bus tickets and passes | BLOCKED BY PROVIDER APPROVAL | Needs BMTC agreement |
| 26 | Metro QR tickets | BLOCKED BY PROVIDER APPROVAL | Needs ONDC onboarding |
| 27 | Payments | BLOCKED BY PROVIDER APPROVAL | Needs gateway and ticketing agreement |
| 28 | NCMC operations | BLOCKED BY PROVIDER APPROVAL | Bank/NPCI domain |
| 29 | Accounts, password reset | NOT IMPLEMENTED | Waiting for Neon credentials and an email provider |
| 30 | Facilities, notifications, AI assistant | NOT IMPLEMENTED | Planned |
| 31 | Admin roles (per-person accounts) | NOT IMPLEMENTED | Single admin key today |

No open item is classified SECURITY ISSUE after the fixes in this audit; remaining risks are listed in
`SECURITY_AUDIT_4_0.md`.

## Defects found and fixed in this audit
| Defect | Fix | Retest |
|---|---|---|
| Scrollable tables not reachable by keyboard (WCAG, serious) | `tabindex`, `role=region` and a label on all 8 tables | axe rescan clean; new static test |
| Server access log recorded searches and "near me" coordinates with IP addresses | `--no-access-log` in the container start script | Script reviewed; local server run with the flag |
| No way for a person to erase their data | `DELETE /api/my-data` and a "Delete my data" control with confirmation | 2 API tests; Edge workflow |
| Live HTTPS site sent no HSTS header | HSTS on HTTPS responses | New test; live site still needs a deploy |

## What was not tested, and why
- **Real Android device and emulator:** not available in this environment. Owner to test; checklist in
  `GOVERNMENT_SUBMISSION_STATUS.md`.
- **4.0 staging URL:** not created yet (owner action on Render).
- **Postgres:** accounts not built; CI does not yet run on Postgres.
- **Database outage and server restart under load:** not exercised in this audit.
- **Full-size Bengaluru data:** performance was measured on demo-sized feeds only.
