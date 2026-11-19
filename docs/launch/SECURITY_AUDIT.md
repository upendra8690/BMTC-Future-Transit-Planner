# Security audit — 4.0.0-beta.1 (17 November 2026)

Based on OWASP Top 10 and the OWASP API Security Top 10. This release's evidence comes from the commands in
[TEST_RESULTS.md](TEST_RESULTS.md). The full 4.0 audit, with findings S1–S10, is in
`docs/government/SECURITY_AUDIT_4_0.md`. This is a self-assessment, not an independent penetration test.

| Area | Control in the app | Evidence | Result |
|---|---|---|---|
| Authentication (admin) | `X-Admin-Key` compared with `hmac.compare_digest`; admin disabled when no key is set | Probes: wrong key 401, no key 401 | Pass; one shared key (S5, open) |
| Passenger accounts | None yet; device data uses a random device key stored as a SHA-256 hash | — | Not applicable until accounts exist |
| Authorisation and owner isolation | Saved routes, scenarios and preferences are filtered by device-key hash | pytest: other device cannot read, delete or erase; probes | Pass |
| Input validation | Pydantic models; length, range and pattern limits on every query (`modes`, `q`, capability name) | pytest 422 cases; probes | Pass |
| SQL injection | SQLAlchemy bound parameters only; no string-built SQL | Injection-shaped probes; bandit | Pass |
| XSS | Every value escaped before HTML is built; CSP `script-src 'self'` | Stored-XSS probe in a real browser | Pass; `style-src 'self'` with no inline styles (S4 fixed 19 Nov 2026) |
| CSRF | No cookies or ambient credentials; keys travel in headers the browser does not add on its own | Design review | Not applicable |
| Rate limiting | Per-client limit (default 120 requests per minute), behind Render's proxy per visitor | pytest `test_rate_limit.py`; 429 observed in the browser run | Pass |
| Secrets | Read from environment only; `.env` and `data/` git-ignored; Render generates `ADMIN_API_KEY` | `render.yaml`; repository search | Pass |
| CORS | No cross-origin access unless `CORS_ORIGINS` is set | Probes | Pass |
| File uploads | Admin only; ZIP only; size limit; ZIP-bomb and path checks | Probes: non-ZIP and ZIP bomb rejected | Pass |
| Error leakage | Error bodies carry a message, never a stack trace | Probes; path-traversal attempts | Pass |
| Logging of sensitive data | uvicorn access log off; the app logs path without query string | `scripts/container_start.sh` | Pass |
| Backups | Admin backup with integrity check for SQLite | pytest `test_maintenance.py` | Pass locally; **gap** on hosted Postgres (not configured) |
| Dependencies | Pinned requirements | pip-audit: no known vulnerabilities; bandit: no issues | Pass |
| Location | Used only when the person taps "Stops near me"; sent with that request only; never stored | Code review; privacy policy | Pass |
| Privacy and deletion | `DELETE /api/my-data` erases the device's server data; the audit entry stores counts only | pytest | Pass |
| Provider actions (tickets, payments, live) | Single refusing adapter; no fake output possible | pytest `test_launch.py` (6 cases) | Pass |
| Travel assistant | Rules only, no language model, so no prompt-injection surface; it can only choose one of the app's own read requests | pytest (16 cases) | Pass |
| Transport security | HSTS on HTTPS; security headers on every response | `test_security_headers.py`; probes | Pass |

## Open findings
| ID | Finding | Severity | Plan |
|---|---|---|---|
| S4 | CSP allowed inline styles (`style-src 'unsafe-inline'`) | Low | Fixed 19 Nov 2026: no inline styles; `style-src 'self'`; tested by `test_the_dashboard_policy_allows_no_inline_styles` and `tests/browser/map_and_policy_check.py` |
| S5 | One shared admin key, so admin actions cannot be traced to a person | Medium | Per-person admin accounts with roles, once accounts exist |
| — | No hosted database backups | Medium (for a pilot) | Configure on the Postgres provider before any pilot |
| — | Free hosting has no persistent disk; device data is lost on restart | Medium (for a pilot) | Persistent Postgres before any pilot |
| — | No independent penetration test | — | Before any production use |

No critical or high findings are open.
