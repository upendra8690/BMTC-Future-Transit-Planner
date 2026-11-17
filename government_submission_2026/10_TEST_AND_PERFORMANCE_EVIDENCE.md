# 10 Test and performance evidence

Every result below comes from a real run.
- **Test machine:** Windows 11, Microsoft Edge driven by Playwright, fresh databases loaded with the demonstration
  feeds.
- **Rate limit:** raised for the browser suites, because they send hundreds of requests a minute. The limit itself is
  tested separately.
- **Detailed reports:** `V4_END_TO_END_TEST_REPORT.md` and `docs/launch/TEST_RESULTS.md`.

## Which code was tested
- The application code (`backend/`, `dashboard/`, `android/`) has **not changed** since commit `d34f347`, which the
  browser, accessibility, security and load suites tested on 17 Nov 2026.
- The final commit adds documents, an Android workflow guard and four tests for that guard.
- Lint, the full unit and API suite, and bandit were **run again on the final code** on 18 Nov 2026.

## Results
| # | Suite | Command | Result | Run on |
|---|---|---|---|---|
| 1 | Lint | `python -m ruff check .` | All checks passed | Final code |
| 2 | Unit, API, integration, migration and static front-end tests | `python -m pytest -p no:cacheprovider` | **429 passed, 5 skipped, 0 failed** | Final code |
| 3 | Static security analysis | `python -m bandit -r backend/app` | No issues | Final code |
| 4 | Release guard (a push cannot publish an Android release) | `python -m pytest tests/test_release_guard.py` | 4 passed; the same tests fail against the old workflow | Final code |
| 5 | Browser regression, 3.0 and 4.0 | `python tests/browser/run_browser_checks.py --chrome <msedge.exe>` | 121 passed, 0 failed | d34f347 |
| 6 | Launch screens, 4 languages, phone and desktop | `python tests/browser/launch_check.py <url>` | 264 of 264 | d34f347 |
| 7 | End-to-end crawl, forms, user journey, PWA, labels | `python tests/browser/e2e_check.py <url> <admin-key-file> <report>` | 486 of 486; **321 controls, 0 decorative or broken** | d34f347 |
| 8 | Accessibility (axe-core, WCAG 2.1 A/AA and best practice) | `python tests/audit/audit_a11y.py <axe.min.js>` | No violations on 15 screens in 2 themes | d34f347 |
| 9 | Security probes against a running server | `python tests/audit/security_probes.py <admin-key-file>` | 34 passed, 0 failed | d34f347 |
| 10 | Dependency vulnerabilities | `python -m pip_audit -r requirements.txt` | No known vulnerabilities found | Final dependencies, 18 Nov 2026 |
| 11 | Load | `python tests/audit/load_audit.py` | 1 user: 90 requests, 0 errors, p95 47 ms. 20 concurrent users: 900 requests, 0 errors | d34f347 |
| 12 | External links | All 18 unique links opened in Edge | 18 of 18 returned status 200 | 17 Nov 2026 |
| 13 | Android shell, static check | `python android/check_starter.py` | Dart grammar 0 errors; 10 of 10 required behaviours present | d34f347 |
| 14 | GitHub Actions CI: tests on Python 3.12 and 3.13, then a container build and smoke test | Runs on every push | Running when this was written; the result is recorded in `FINAL_SUBMISSION_READINESS.md` | GitHub |
| 15 | Android build in GitHub Actions (analyse and compile only; nothing published) | Runs on a push that changes `android/` | Running when this was written; the result is recorded in `FINAL_SUBMISSION_READINESS.md` | GitHub |

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
