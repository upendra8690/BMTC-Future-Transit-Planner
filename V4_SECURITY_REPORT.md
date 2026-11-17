# V4 security report — 17 November 2026

A self-assessment against OWASP Top 10 and the OWASP API Security Top 10. It is not an independent penetration test.
Commands and numbers are in [V4_END_TO_END_TEST_REPORT.md](V4_END_TO_END_TEST_REPORT.md). The detailed control
table is in `docs/launch/SECURITY_AUDIT.md`.

| Area | Result | Evidence |
|---|---|---|
| Authentication — admin | PASS | Constant-time key comparison; wrong or missing key 401 (probes); wrong key refused in the browser (e2e) |
| Authentication — passengers | NOT IMPLEMENTED | No accounts. Data is tied to a random device key, stored on the server only as a SHA-256 hash |
| Authorisation and data isolation | PASS | Another device cannot read, delete or erase this device's data (pytest, probes, e2e) |
| SQL injection | PASS | Bound parameters only (bandit clean); injection-shaped input probes |
| XSS | PASS | All values escaped; CSP `script-src 'self'`; stored-XSS probe in a real browser. Open: `style-src 'unsafe-inline'` (S4, low) |
| CSRF | Not applicable | No cookies or ambient credentials; keys travel in headers a browser does not add on its own |
| Rate limiting | PASS | Per-client limit, default 120 per minute (pytest); HTTP 429 observed during this work |
| API validation | PASS | Lengths, ranges and patterns on every input (pytest 422 cases; e2e form checks) |
| Secrets | PASS | Environment only; `.env` and `data/` git-ignored; Render generates `ADMIN_API_KEY`; secret scan of the commit found nothing |
| Permissions (location) | PASS | Asked only on "Stops near me"; refusal handled with a message and nothing sent (e2e); not stored |
| Privacy | PASS | No access log; no analytics; Delete my data verified end to end (server rows, device lists, device key) |
| Database backups | PARTIAL | Admin SQLite backup with integrity check works (regression); hosted Postgres backups not configured |
| Dependencies | PASS | pip-audit: no known vulnerabilities; bandit: no issues |
| Provider actions (tickets, payments, live) | PASS | One refusing adapter; no fake output possible (pytest, e2e) |
| Android shell | PARTIAL | Navigation is limited to the planner's host; external links now go to the system browser or dialler. Not compiled |

## Demo data cannot be confused with official data
| Check | Result |
|---|---|
| Only sources of kind OFFICIAL can be verified; demo sources are SYNTHETIC_DEMO | PASS — e2e: an administrator's attempt to verify the demo source was refused |
| The default classification is Officially verified, which shows no data and says so | PASS — e2e unhappy paths |
| No demo route, stop or station carries the "Officially verified" badge | PASS — e2e |
| Every journey ride carries its "Unverified feed" badge and source name | PASS — e2e step 3 |
| `/api/data-status` reports `demo_only: true` and no live feed | PASS — e2e |
| Demo names are all "Demo …" and the agency is "Demo Transit (SYNTHETIC)" / "Demo Metro (SYNTHETIC)" | PASS — inspected |

## Open findings
| ID | Finding | Severity | Next action |
|---|---|---|---|
| S5 | One shared admin key, so admin actions cannot be traced to a person | Medium | Per-person admin accounts after passenger accounts |
| — | Free hosting: no persistent database, no backups | Medium (for a pilot) | Neon Postgres with backups before any pilot |
| A1 | Android shell link and back-button fix not compiled | Medium | Build the v4 APK and test on a phone |
| S4 | CSP allows inline styles | Low | Move inline `style=` attributes to CSS classes |
| — | No independent penetration test | — | Before production use |
