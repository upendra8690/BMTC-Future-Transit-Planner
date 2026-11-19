# Security audit — 4.0.0-alpha.3

Date: 16 November 2026. Scope: FastAPI backend, web app/PWA, deployment scripts, live 3.0 headers. Method: automated
scans (`pip-audit`, `bandit`, `ruff` security rules), 33 scripted probes against a running server
(`tests/audit/security_probes.py`), a stored-XSS test in Microsoft Edge, and code review. This is an internal
assessment, not a certification or a professional penetration test.

## Controls verified (probe results)
| Area | Result |
|---|---|
| Security headers (page and API): X-Frame-Options DENY, nosniff, Referrer-Policy, CSP with `script-src 'self'`, `frame-ancestors 'none'` | Pass |
| CORS: no `Access-Control-Allow-Origin` for another site | Pass |
| Admin API: no key → 401, wrong key → 401, correct key → 200 | Pass |
| Object-level access: device B cannot list or delete device A's saved route | Pass |
| SQL-injection-shaped searches (`' OR 1=1--`, `UNION SELECT`, `\`, `_%_`) | Return no rows and no error |
| Input validation: over-long search and too-short journey names | 422 |
| Path traversal and secret files (`/../backend/...`, `%2e%2e`, `/.env`, database file) | Nothing leaked |
| Upload safety: non-ZIP rejected; 60 MB highly compressed file rejected | Pass |
| Stored XSS: feed with `<img onerror>`, `<script>` and `<svg onload>` in names | Shown as text; no script ran (Edge) |
| Injected inline script blocked by CSP | Confirmed (the audit's own injection was blocked until bypassed for the scan) |
| Dependencies (`pip-audit`) | No known vulnerabilities |
| Static analysis (`bandit -r backend scripts`) | No issues reported |

## Findings
| ID | Finding | Severity | Evidence | Fix | Retest |
|---|---|---|---|---|---|
| S1 | Server access log recorded search text and "stops near me" coordinates with the client IP | Medium (privacy) | `docs/PRIVACY.md` (Logs); uvicorn default access log | Container starts uvicorn with `--no-access-log`; app logs only method, path without query, status and time for changes | Fixed in code; effective on the next deploy |
| S2 | No erasure: a person could not delete their server-side data | Medium (privacy/DPDP) | No endpoint existed | `DELETE /api/my-data` + UI with confirmation; audit entry stores counts only, no IP | 2 API tests; Edge workflow 4/4 |
| S3 | Live HTTPS site sends no `Strict-Transport-Security` | Low | Header check of the live 3.0 site: absent | HSTS (1 year) on HTTPS responses | Unit test; live retest after deploy |
| S4 | CSP allows `'unsafe-inline'` styles | Low | `DASHBOARD_CSP` | Fixed 19 Nov 2026: no inline styles; `style-src 'self'`; tested by `test_the_dashboard_policy_allows_no_inline_styles` and `tests/browser/map_and_policy_check.py` | — |
| S5 | One shared admin key; no per-person accounts, MFA or lockout | Medium (accountability) | `docs/SECURITY_ASVS.md` V6 | Open: role-based admin accounts planned | — |
| S6 | Probe expected 400 for saved-routes list without a device key; app returns an empty list | Informational | Probe output | None needed: nothing is disclosed; writes without a key are refused | Probe expectation corrected |
| S7 | Rate limit is in memory, per instance; resets on restart | Low | `security.py` | Accepted for a single-instance demo; use a shared store if scaled out | — |
| S8 | Android APK signed with a debug key | Medium (distribution) | APK workflow | Owner to create a release key in GitHub secrets | — |
| S9 | Free hosting: no persistent database, no backups for user data, no WAF | Medium (availability) | Render free tier behaviour | Neon Postgres (planned); document limits | — |
| S10 | Device identity is a browser-held random key; anyone with it can act as that device | Low | Design | Accepted for guest mode; accounts will use server sessions | — |

## Not covered
Professional penetration test; authenticated user accounts (not built); payment flows (disabled, no gateway);
Android binary analysis; infrastructure of the hosting provider.
