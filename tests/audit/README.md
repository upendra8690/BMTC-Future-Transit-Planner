# Audit scripts (4.0 government-readiness audit)

These scripts produced the evidence in `docs/government/`. They run against a **running** server and are not part of
`pytest`.

| Script | What it measures | How to run |
|---|---|---|
| `audit_a11y.py` | axe-core WCAG 2.1 A/AA + best-practice scan of every 4.0 screen, light and dark, phone size | Start a demo server on port 8020, then `python tests/audit/audit_a11y.py tests/browser/vendor/axe-core/axe.min.js` |
| `security_probes.py` | Security headers, CORS, admin auth, device data isolation, injection-shaped input, path traversal, upload limits, stored XSS in a real browser | Start a demo server on port 8030 with `ADMIN_API_KEY` set (key also saved in a file) and a raised `RATE_LIMIT_PER_MINUTE`, then `python tests/audit/security_probes.py <keyfile>` |
| `load_test.py` | Latency and errors with 1 and 20 concurrent users over a realistic request mix | Same server as above |

All three use Microsoft Edge through Playwright (`pip install -r requirements-browser.txt`). Seed the server's database
with `python scripts/seed_demo_feed.py`.
