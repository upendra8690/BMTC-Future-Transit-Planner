# 10 Test and performance evidence

Every result below comes from a real run.
- **Test machine:** Windows 11, Microsoft Edge driven by Playwright, fresh databases loaded with the demonstration
  feeds.
- **Rate limit:** raised for the browser suites, because they send hundreds of requests a minute. The limit itself is
  tested separately.
- **Detailed reports:** `V4_END_TO_END_TEST_REPORT.md` and `docs/launch/TEST_RESULTS.md`.

## Which code was tested
Unless the last column says otherwise, every suite was run on the final code of the commit that contains this
document, on 18 Nov 2026. The application changed again in this round: real mode separated from demonstration mode, the community Namma Metro
timetable, and exact stop-name matching. So every suite below was run again on the final code.

## Results
| # | Suite | Command | Result | Run on |
|---|---|---|---|---|
| 1 | Lint | `python -m ruff check .` | All checks passed | Final code |
| 2 | Unit, API, integration, migration and static front-end tests | `python -m pytest -p no:cacheprovider` | **470 passed, 5 skipped, 0 failed** | Final code |
| 3 | Static security analysis | `python -m bandit -r backend/app` | No issues | Final code |
| 4 | Release guard (a push cannot publish an Android release) | `python -m pytest tests/test_release_guard.py` | 4 passed; the same tests fail against the old workflow | Final code |
| 5 | Browser regression, 3.0 and 4.0 | `python tests/browser/run_browser_checks.py --chrome <msedge.exe>` | 121 passed, 0 failed; other browser problems: 0 | Final code |
| 6 | Launch screens, 4 languages, phone and desktop | `python tests/browser/launch_check.py <url>` | 268 of 268 | Final code |
| 7 | End-to-end crawl, forms, user journey, PWA, labels | `python tests/browser/e2e_check.py <url> <admin-key-file> <report>` | 1,028 of 1,028; **869 controls, 0 decorative or broken** (demonstration server) | Final code |
| 8 | Accessibility (axe-core, WCAG 2.1 A/AA and best practice) | `python tests/audit/audit_a11y.py <axe.min.js>` | No violations on 15 screens in 2 themes | Final code |
| 9 | Security probes against a running server | `python tests/audit/security_probes.py <admin-key-file>` | 34 passed, 0 failed | Final code |
| 10a | Real-mode screens, as the public service runs: no demo data, a real Metro journey with approximate times and no fare, one entry per station, ODbL attribution | `python tests/browser/real_mode_check.py <url>` | 14 of 14 | Final code |
| 10 | Upcoming-transport editor, year banner, Kannada labels, at 390 px | `python tests/browser/upcoming_admin_check.py <url> <admin-key-file>` | 17 of 17 | Final code |
| 11 | Deployment checker against a local server | `python scripts/verify_deployment.py http://127.0.0.1:8020` | Every application check passes. The HTTPS and HSTS checks fail on a laptop without TLS, as expected; they must pass on the public address | Final code |
| 12 | Container start script with a Render-style `PORT` | `PORT=8061 SEED_DEMO_FEED=1 sh scripts/container_start.sh` | Listened on 8061, loaded both demo feeds, reported 4.0.0-beta.1 | Final code |
| 13 | Dependency vulnerabilities | `python -m pip_audit -r requirements.txt` | No known vulnerabilities found | 18 Nov 2026 (dependencies unchanged since) |
| 14 | Load | `python tests/audit/load_audit.py` | 1 user: 90 requests, 0 errors, p95 47 ms. 20 concurrent users: 900 requests, 0 errors | d34f347 (the planner has not changed since) |
| 15 | External links | All 18 unique links opened in Edge | 18 of 18 returned status 200 | 17 Nov 2026 |
| 16 | Android shell, static check | `python android/check_starter.py` | Dart grammar 0 errors; 10 of 10 required behaviours present | d34f347 (Android code unchanged since) |
| 17 | GitHub Actions CI: tests on Python 3.12 and 3.13, then a container build and smoke test | Runs on every push | Success for `ab94f8a` (push and pull request). For the final commit, see `FINAL_SUBMISSION_READINESS.md` | GitHub |
| 18 | Android build in GitHub Actions (analyse and compile only; nothing published) | Runs on a push that changes `android/` | Success for `ab94f8a`; the only release is still the 3.0 `app-latest` | GitHub |
| 19 | Live 3.0 service unchanged | The `--v3` checks of `scripts/verify_deployment.py` | Health 200; no `/api/features` (so still 3.0); page title "BMTC Future Transit Planner" | 18 Nov 2026 |

**Docker.** Docker is not installed on the test machine, so the image itself is built only in GitHub Actions. The CI
container job builds it, starts it with `PORT=10000` as Render does, and checks the 4.x version, the page title,
upcoming transport, the data status, a journey, a refused payment and the security policy.

**Found and fixed by these runs.** In the new admin editor, a form field named `id` hid the form's own id. The app's
submit handler then missed the form, and the browser submitted it as a plain page load, with the entry's fields in
the address bar. The browser check (row 10) found it. The field is now `entry_id`, and a static test forbids control
names that hide form properties.

The 5 skipped tests check PDF export in Kannada and other scripts. They need the DejaVu Sans font, which is not
installed on the test machine.

## The passenger journey tested end to end (phone size, 390 × 844)
| Step | Result |
|---|---|
| The app opens on Home | PASS |
| Bus-only journey; every ride is a bus, labelled "Unverified feed" and "not live" | PASS |
| Route page: stops, timetable, open a stop | PASS |
| Metro-only journey | PASS |
| Bus + Metro journey with a walk between them | PASS |
| Save the journey, list it in Favourites, plan it again | PASS |
| Switch to Kannada | PASS |
| Refresh: the language and saved items remain | PASS |
| Offline: app shell and saved journeys open; planning shows an error with Retry | PASS |
| Every screen fits 390 px | PASS |

## Failure cases tested
- An unknown stop.
- No journey for the chosen mode.
- No official data.
- A server error.
- A dropped connection.
- Too-short or empty input.
- An over-long question.
- A question about live arrival times.
- Requests for tickets, QR codes and payments.
- Location refused.
- A wrong administrator key.

Each produced a clear message, and none produced invented data.

## Not tested
- A real Android phone.
- A real screen reader.
- Native-speaker review of the translations.
- Production hosting under load.
- An independent penetration test.
