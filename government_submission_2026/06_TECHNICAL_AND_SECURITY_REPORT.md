# 06 Technical and security report

This is a self-assessment against the OWASP Top 10 and the OWASP API Security Top 10. **It is not an independent
penetration test.** Commands and results are in [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md). Detailed reports in the
repository: `V4_SECURITY_REPORT.md` and `docs/launch/SECURITY_AUDIT.md`.

## Controls
| Area | Result | How it was checked |
|---|---|---|
| Administrator authentication | PASS | Constant-time key comparison. A wrong or missing key gets 401 (probes); a wrong key is refused in the browser (e2e) |
| Passenger authentication | NOT IMPLEMENTED | There are no accounts. Data is tied to a random device key, stored on the server only as a SHA-256 hash |
| Authorisation and data isolation | PASS | One device cannot read, delete or erase another device's data (pytest, probes, e2e) |
| SQL injection | PASS | Bound parameters only; bandit is clean; probes with injection-shaped input |
| Cross-site scripting | PASS | All values are escaped; the content security policy allows scripts only from the app itself; a stored-XSS probe ran in a real browser |
| CSRF | Not applicable | No cookies or ambient credentials; keys travel in headers that a browser never adds on its own |
| Transport security | PASS | HSTS and security headers on every response (pytest); hosting supplies HTTPS |
| Rate limiting | PASS | Per-client limit, default 120 requests per minute, with 429 and `Retry-After` (pytest) |
| Input validation | PASS | Lengths, ranges and patterns on every input (pytest 422 cases; e2e forms) |
| Secrets | PASS | Taken from the environment only; `.env` and data folders are not in Git; Render generates the admin key; a secret scan of the commits found nothing |
| Location permission | PASS | Asked only on "Stops near me". A refusal gets a message and nothing is sent; the location is never stored |
| Dependencies | PASS | pip-audit: no known vulnerabilities; bandit: no issues |
| Provider actions | PASS | One refusing adapter per capability; tests prove no ticket, QR, receipt, balance or payment field can be returned |
| Release safety | PASS | A push to `v4` cannot publish an Android release (workflow guard and `tests/test_release_guard.py`) |
| Database backups | PARTIAL | The administrator SQLite backup with integrity check works; hosted PostgreSQL backups are not configured yet |
| Android shell | PARTIAL | Navigation stays on the planner's own address; telephone and official links open in the dialler or browser. Not tested on a phone |

## Demonstration data cannot be passed off as official
| Check | Result |
|---|---|
| Only a source of kind OFFICIAL can be verified, and demo sources are SYNTHETIC_DEMO | PASS. e2e: an administrator's attempt to verify the demo source was refused |
| The default view is "Officially verified", which shows no data and says so | PASS |
| No demo route, stop or station shows the "Officially verified" badge | PASS |
| Every ride in a journey shows "Unverified feed" and its source | PASS |
| `GET /api/data-status` reports `demo_only: true` and no live feed | PASS, also checked in the CI container job |
| Demo names all begin "Demo …"; the agencies are "Demo Transit (SYNTHETIC)" and "Demo Metro (SYNTHETIC)" | PASS (inspected) |

## Open findings
| ID | Finding | Severity | Planned action |
|---|---|---|---|
| S5 | One shared administrator key, so actions cannot be traced to a person | Medium | Separate administrator accounts once passenger accounts exist |
| H1 | Free hosting has no persistent database and no backups | Medium for a pilot | Paid hosting and PostgreSQL with daily backups before any pilot |
| A1 | Android shell not tested on a phone | Medium | Test calls, links and the back button on a real phone |
| S4 | The content security policy still allows inline styles | Low | Move the remaining inline styles into the stylesheet |
| — | No independent penetration test | — | Before any production use; we welcome a review by the authority's security team |

## Performance
Load test against a local server:
- 1 user: 90 requests, 0 errors, 95th-percentile response time 47 ms.
- 20 concurrent users: 900 requests, 0 errors.

These numbers come from a laptop with demonstration data, not from production hosting. On the free hosting plan the
first request after an idle period can take up to a minute while the server wakes; on 17 Nov 2026 the 3.0 service took
53 seconds to wake.
