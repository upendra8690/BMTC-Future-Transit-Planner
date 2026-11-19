# Security audit: Bengaluru Transit Planner 4.0

A self-assessment on 19 November 2026 (branch `v4`). **It is not an independent penetration test,** and passing
automated checks does not make the application secure. An independent test is recommended before any public-sector
production use. The full checklist (OWASP ASVS, API Top 10, MASVS, DPDP, GIGW, CERT-In) is
`government_submission_2026/20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md`.

## Checks run on this commit
| Check | Result |
|---|---|
| ruff (code quality, including security-relevant rules) | All checks passed |
| bandit, medium and high severity | No issues |
| pip-audit (pinned dependencies) | Runs in CI on every push; no known vulnerabilities on 18 Nov 2026 |
| Secret scan of every commit | No real secret (only the throwaway password of CI's temporary database) |
| Security probes against a running server (`tests/audit/security_probes.py`) | 34 of 34 on `fb8d2a2`; not repeated on this commit |
| Rate limit behind the hosting proxy (R1) | Fixed and verified on the public service, 18 Nov 2026 |

## Controls
| Area | Control |
|---|---|
| Administrator access | Long random key from the host, compared in constant time; editor and admin roles for accounts (off). The key is held in browser memory only, never stored |
| Session security | Accounts (off): hashed bearer tokens, 30-day expiry, lockout after 8 failures |
| Authorisation | Device-scoped data cannot be read or deleted by another device; admin routes need the key or an admin or editor role |
| Injection | SQLAlchemy bound parameters only |
| Cross-site scripting | Every value escaped before display; links pass `safeHref` (http and https only); CSP `script-src 'self'` |
| CSRF | Not applicable: no cookies; credentials travel in headers a browser never adds itself |
| SSRF | The server fetches no address supplied by a user |
| Rate limiting | 120 requests a minute per visitor, counted by the hosting edge's visitor address |
| File uploads | GTFS ZIPs (administrators only): size, member count, decompressed size and compression ratio limits |
| Secrets | Hosting environment only; never in the frontend or the repository |
| Logging | No access log (searches and locations are not recorded); administrative actions in the audit log |
| Privacy | No names, phone numbers, locations or payment data stored; location used once on tap |

## New in this round: review of the Phase 2 features
| Feature | Risk considered | Control |
|---|---|---|
| Service notices | False or alarming notices; links to harmful sites | Admin or editor only; link must be an official domain or account (allow-list, tested against look-alike hosts such as `evilgov.in` and `gov.in.example.com`); 31-day limit; reason required; audit log; withdrawal |
| Service notice display | Stored XSS | Text escaped; link through `safeHref`; opened with `rel="noopener noreferrer"` |
| Journey links | Leaking personal data | The link holds only station names, travel mode and data label |
| Start from my location | Location tracking | Asked by the browser on tap; sent once to find the nearest stop; not stored; no access log |
| Browser dialogs | Spoofable prompts | None used; a static test forbids `prompt(` |

## Findings register
| ID | Finding | Severity | Status |
|---|---|---|---|
| R1 | Rate limit could be bypassed behind the hosting proxy | Was medium | **Fixed and verified** (18 Nov 2026) |
| S5 | One shared administrator key | Medium | Open: per-person roles exist and switch on with accounts (needs PostgreSQL) |
| H1 | No permanent database or backups on free hosting | Medium for a pilot | Open: needs the owner's PostgreSQL |
| A1 | Android wrapper not run on a device | Medium | Open |
| S4 | CSP allowed inline styles | Low | Fixed 19 Nov 2026: no inline styles; `style-src 'self'`; tested by `test_the_dashboard_policy_allows_no_inline_styles` and `tests/browser/map_and_policy_check.py` |
| — | "Stops near me" listed station entrances (functional defect) | — | **Fixed** in this round, with a regression test |
| — | No independent penetration test | — | Recommended before production |

## Not claimed
No claim is made that the application is free of vulnerabilities, that it meets GIGW 3.0, or that it is cleared for
government hosting.
