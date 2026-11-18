# 10 Test and performance evidence

Every result below comes from a real run. Each row states the code it was run on and the date.
- **Code under review:** branch `v4`, commit `a97beae` (18 Nov 2026). The documentation commit that adds this file
  changes no application code.
- **Test machine:** Windows 11, Python 3.12; browser suites drive Microsoft Edge through Playwright.
- **Detailed reports:** `V4_END_TO_END_TEST_REPORT.md`, `docs/launch/TEST_RESULTS.md`.

## Results
| # | Suite | Command | Result | Run on |
|---|---|---|---|---|
| 1 | Lint | `python -m ruff check .` | All checks passed | `a97beae`, 18 Nov 2026 |
| 2 | Unit, API, integration, migration and static front-end tests (includes the Android release guard) | `python -m pytest -p no:cacheprovider` | **501 passed, 5 skipped, 0 failed** (180 s) | `a97beae`, 18 Nov 2026 |
| 3 | Static security analysis | `python -m bandit -r backend scripts -ll` | No medium- or high-severity issues | `a97beae`, 18 Nov 2026 |
| 4 | Dependency vulnerabilities | `python -m pip_audit -r requirements-verified.txt --no-deps --disable-pip` | No known vulnerabilities found | 18 Nov 2026 |
| 5 | GitHub Actions CI: tests on Python 3.12 and 3.13; container (demonstration and real mode); PostgreSQL 16 with migrations, data load and a restart-persistence check | Runs on every push | 4 of 4 jobs passed | `a97beae`, 18 Nov 2026 |
| 6 | Public deployment check | `python scripts/verify_deployment.py https://bengaluru-transit-planner-v4.onrender.com --v3 https://bmtc-future-transit-planner-3-0.onrender.com` | **All 14 checks passed** (12 for 4.0, 2 for 3.0). The first try of the 3.0 checks returned HTTP 503 while that free service was asleep; it woke in 18 s, and the rerun passed | Public services, 18 Nov 2026 |
| 7 | Public service: security headers, health, mode, features | Direct requests | CSP, HSTS, X-Frame-Options, Permissions-Policy, Referrer-Policy, COOP and nosniff present; health 200; real mode; accounts reported as switched off | Public service, 18 Nov 2026 |
| 8 | Public service: rate-limit behaviour | A controlled test of about 125 small requests to the health endpoint | **Finding R1** ([20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md)): the limit can be bypassed behind the hosting proxy | Public service, 18 Nov 2026 |
| 9 | Browser regression, 3.0 and 4.0 | `python tests/browser/run_browser_checks.py --chrome <msedge.exe>` | 121 passed, 0 failed | `fb8d2a2`, 18 Nov 2026 |
| 10 | End-to-end crawl, forms, user journey, PWA, labels | `python tests/browser/e2e_check.py <url> <admin-key-file> <report>` | 1,028 of 1,028; 869 controls, 0 decorative or broken (demonstration server) | `fb8d2a2`, 18 Nov 2026 |
| 11 | Launch screens, 4 languages, phone and desktop | `python tests/browser/launch_check.py <url>` | 268 of 268 | `fb8d2a2`, 18 Nov 2026 |
| 12 | Accessibility (axe-core, WCAG 2.1 A/AA) | `python tests/audit/audit_a11y.py <axe.min.js>` | 0 violations on 15 screens in 2 themes | `fb8d2a2`, 18 Nov 2026 |
| 13 | Security probes against a running server | `python tests/audit/security_probes.py <admin-key-file>` | 34 passed, 0 failed | `fb8d2a2`, 18 Nov 2026 |
| 14 | Real-mode screens, as the public service runs | `python tests/browser/real_mode_check.py <url>` | 14 of 14 | Public service, 18 Nov 2026 |
| 15 | Upcoming-transport editor at 390 px | `python tests/browser/upcoming_admin_check.py <url> <admin-key-file>` | 17 of 17 | `fb8d2a2`, 18 Nov 2026 |
| 16 | Load, local server | `python tests/audit/load_audit.py` | 1 user: 90 requests, 0 errors, 95th percentile 47 ms. 20 concurrent users: 900 requests, 0 errors | `d34f347` (planner unchanged since) |
| 17 | Android wrapper | GitHub Actions compile check; `python android/check_starter.py` | Compiles (`ab94f8a`); static check 10 of 10. **Not run on a phone or emulator** | `ab94f8a` |

**Commits after `fb8d2a2`.** Commits `ab725e6` and `aafdc4f` changed database and account code. Accounts stay switched
off on the public service. Rows 1 to 8 cover the final code. The browser suites (rows 9 to 13 and 15) were not
repeated after those two commits.

**Skipped tests.** The 5 skipped tests check PDF export in Kannada and other scripts. They need the DejaVu Sans font,
which is not installed on the test machine. They run in CI on Linux.

## Measured on the public service (18 Nov 2026, from the test machine)
| Measure | Result |
|---|---|
| Page and scripts, compressed | Page 3.2 KB; app script 37 KB; language file 52 KB; styles 6 KB |
| API response time when awake | 0.13 to 0.29 s for typical requests; health 0.27 s |
| Wake-up time on the free plan | Up to a minute (3.0 woke in 18 s on 18 Nov 2026) |

No Lighthouse score has been measured yet.

## The passenger journey tested end to end (phone size, 390 × 844, demonstration server)
| Step | Result |
|---|---|
| The app opens on Home | PASS |
| Bus-only journey; every ride is a bus, labelled "Unverified feed" and "not live" | PASS |
| Metro-only journey | PASS |
| Bus + Metro journey with a walk between them | PASS |
| Save the journey, list it in Favourites, plan it again | PASS |
| Switch to Kannada; refresh: the language and saved items remain | PASS |
| Offline: app shell and saved journeys open; planning shows an error with Retry | PASS |
| Every screen fits 390 px | PASS |

## Failure cases tested
Each produced a clear message, and none produced invented data:
- an unknown stop;
- no journey for the chosen mode;
- no official data;
- a server error and a dropped connection;
- too-short or empty input, and an over-long question;
- a question about live arrival times;
- requests for tickets, QR codes and payments;
- location refused;
- a wrong administrator key.

## Not tested
- A real Android phone, or an Android emulator.
- iPhone and iPad (Safari), Firefox, and screen widths below 390 px.
- A real screen reader.
- Native-speaker review of the translations.
- Production hosting under load.
- An independent penetration test.
