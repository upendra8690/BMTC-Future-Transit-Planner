# Security and privacy plan for 4.0

Builds on `docs/SECURITY_ASVS.md` (OWASP ASVS 5.0.0 self-mapping for 3.0). This plan covers what 4.0 adds.

## Controls already in place (3.0)
Constant-time admin key check; device keys stored as SHA-256; per-IP rate limiting; strict CSP (same-origin scripts);
`X-Frame-Options: DENY`; upload limits (size, ZIP members, compression ratio); parameterised SQL through SQLAlchemy;
audit log of admin actions; no secrets in the repository (`.env` ignored).

## New threats and controls

| Area | Threat | Control (planned) |
|---|---|---|
| Accounts | Credential stuffing, weak passwords | argon2id hashing; login rate limit per IP and per account; generic error messages; minimum length + breached-password check offline list |
| Sessions | Theft, fixation, CSRF | Random session ids stored hashed; httpOnly, Secure, `SameSite=Lax` cookies; rotate on login; CSRF token on state-changing requests; 30-day expiry |
| Authorisation | Reading another user's favourites | Every query scoped by `user_id`; tests for cross-user access (IDOR) |
| Admin | Shared key, privilege misuse | Admin accounts with roles; audit every action; key only for bootstrap |
| Input | XSS, injection | Existing CSP; text rendered with `textContent`; Pydantic validation; ORM queries only |
| Location | Tracking users | Location used in the browser for "near me"; only the coordinates of a single request reach the server and are not logged or stored |
| Live data | Spoofed or stale feeds | Feeds only from configured HTTPS URLs; freshness thresholds; positions never invented |
| Payments (future) | Fake "paid" states, replay, double charge | Server-side verification only; webhook signatures; unique provider event ids; idempotency keys; no card/CVV/UPI PIN storage; tickets issued only after provider confirmation |
| SOS | False sense of safety | Never claims an alert was sent unless a provider confirms; always offers `tel:112` |
| AI | Prompt injection, invented facts | Assistant can only call read-only tools; answers must cite tool results; no admin tools |
| Supply chain | Vulnerable packages | `pip-audit` and Dependabot in CI; pinned versions in `requirements-verified.txt` |
| Android | WebView abuse | Only the planner's host loads; no JavaScript bridge exposes secrets; release signing key never in git |
| Secrets | Leaks | Environment variables / GitHub secrets only; `.env` ignored; secret scanning on the repo |
| Backups | Loss of accounts | Postgres provider backups (D3) plus a documented export |

## Privacy

- Collect only: email, password hash, display name (optional), language, saved items.
- No phone number, no SMS, no tracking pixels or third-party analytics.
- Account deletion removes personal data immediately; data export as JSON.
- Privacy policy and terms pages in the app (Phase 11), reviewed by you (not legal advice).
- Retention periods in `DATABASE_DESIGN_4.0.md`.

## Known gaps to accept for a ₹0 demo
- Free hosting has no WAF or DDoS protection beyond the provider's defaults.
- No professional penetration test; the OWASP mapping is a self-assessment.
