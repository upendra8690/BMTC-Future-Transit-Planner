# 20 Cybersecurity, privacy, accessibility, reliability and data-governance checklist

A self-assessment of version 4.0.0-beta.1 (branch `v4`, code of commit `a97beae`), made on 18 November 2026. **It is
not an independent penetration test or a security audit.** No claim is made that the application is free of
vulnerabilities. Evidence is in [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md) and [06](06_TECHNICAL_AND_SECURITY_REPORT.md).

| Status | Meaning |
|---|---|
| **MET** | In place and tested |
| **PARTIAL** | Partly in place; the note says what is missing |
| **OPEN** | A known gap, listed in section 4 |
| **N/A** | Not applicable to the current scope |
| **AUTHORITY** | A decision for the authority |

## 1. Application security (OWASP ASVS 5.0 areas)
| Area | Status | Notes |
|---|---|---|
| Architecture and trust boundaries | MET | One server, one database; providers not connected; see [05](05_SYSTEM_ARCHITECTURE.md) |
| Administrator authentication | PARTIAL | Long random key, compared in constant time; wrong key gets 401. One shared key, so actions are not traceable to a person (S5) |
| Passenger authentication | N/A today | Accounts are built and tested (scrypt password hashes, 30-day bearer sessions stored as hashes, lockout after 8 failures, recovery codes) but **switched off** on the public service |
| Access control | MET | One device cannot read or delete another's items; editor and admin roles exist for accounts |
| Injection (SQL) | MET | Bound parameters through SQLAlchemy only; probes with injection-shaped input |
| Cross-site scripting | MET | Values escaped before display; scripts only from the app's own address (content security policy) |
| CSRF | N/A | No cookies; credentials travel only in headers a browser never adds by itself |
| Transport security | MET | HTTPS from the host; HSTS and security headers present on the public service (checked 18 Nov 2026) |
| Security headers | PARTIAL | CSP, HSTS, X-Frame-Options DENY, Permissions-Policy, Referrer-Policy, COOP, nosniff all present. The CSP still allows inline styles (S4) |
| File upload (GTFS import, administrators only) | MET | Size, member count, decompressed size and compression ratio checked before reading |
| Rate limiting | MET | 120 requests a minute per visitor, counted by the address the hosting edge reports (R1 fixed and verified on the public service, 18 Nov 2026) |
| Error handling and logging | PARTIAL | No access log, so searches and locations are not recorded. Administrative actions are in an audit log. See section 6 for the government logging question |
| Dependencies | MET | pip-audit: no known vulnerabilities; versions pinned in `requirements-verified.txt` |
| Static analysis | MET | ruff clean; bandit: no medium- or high-severity issues |
| Secrets | MET | Only in the hosting environment. A scan of every commit found no real secret (the only match is a throwaway password for the temporary database inside automated tests) |

## 2. API security (OWASP API Security Top 10, 2023)
| Risk | Status | Notes |
|---|---|---|
| API1 Object-level authorisation | MET | Device and account scoping tested |
| API2 Authentication | PARTIAL | See S5 |
| API3 Property-level authorisation | MET | Response models list the fields returned; no provider field can appear |
| API4 Resource consumption | MET | Per-visitor limit (R1 fixed); request sizes and query lengths are limited |
| API5 Function-level authorisation | MET | Every administrative route requires the key or an admin role |
| API6 Sensitive business flows | N/A | No tickets or payments |
| API7 Server-side request forgery | MET | The server fetches no address supplied by a user |
| API8 Security misconfiguration | PARTIAL | S4 |
| API9 Inventory | MET | 67 operations documented in OpenAPI at `/api/docs` |
| API10 Unsafe consumption of APIs | N/A | No third-party API is called |

## 3. Android wrapper (OWASP MASVS 2 categories)
**Not tested on a phone or emulator yet** (finding A1).

| Category | Status | Notes |
|---|---|---|
| Storage | PARTIAL | The wrapper stores nothing itself; the web view keeps the web app's own device storage. Android backup is left at its default (A6) |
| Cryptography | N/A | No cryptography in the wrapper |
| Authentication | N/A | Accounts are off |
| Network | MET (by code) | Only the planner's own address loads inside the app; Android blocks plain HTTP by default |
| Platform interaction | PARTIAL | Phone links open the dialler and official websites open the browser; no JavaScript bridge. Location is not wired (A2) |
| Code quality | PARTIAL | The release build is signed with a debug key and no Play bundle (AAB) is built (A5) |
| Resilience | N/A | No secrets or payments in the app |
| Privacy | MET (by code) | Only the internet permission is requested |

## 4. Open findings register
| ID | Finding | Severity | Affects | Status |
|---|---|---|---|---|
| R1 | **Fixed and verified (18 Nov 2026, commit `5ef03ed`).** The per-visitor request limit trusted the first X-Forwarded-For entry, which a visitor can write, so it could be bypassed and its client table filled. It now counts visitors by CF-Connecting-IP, which Render's Cloudflare edge sets. Live test: 120 requests with a forged X-Forwarded-For used up the sender's own budget; a forged CF-Connecting-IP is refused by the edge (HTTP 403) | Was medium | Public service, all `/api/` routes | Closed |
| S5 | One shared administrator key | Medium | Administration | Per-person admin accounts, once a permanent database exists |
| H1 | Free hosting: no permanent database, no backups; the disk is erased on restart | Medium for a pilot | Saved routes on the server; upcoming-transport edits | Paid hosting and PostgreSQL with daily backups before any pilot |
| A1 | Android wrapper not tested on a phone or emulator | Medium | Android | Emulator test, then a phone test |
| A2 | "Stops near me" does not work inside the Android wrapper | Medium (function) | Android | Location permission, asked only when the passenger taps the button |
| A5 | Android release build signed with a debug key; no Play bundle | Medium (release readiness) | Android | Release key held by the applicant; AAB build |
| A6 | Android backup setting not reviewed | Low | Android | Disable backup of web data, or review it |
| S4 | CSP allows inline styles | Low | Web app | Move inline styles into the stylesheet |
| — | No independent penetration test | — | All | Before any production use; the authority's security team is welcome to review |

**Accuracy of labels** (trust findings, confirmed on 18 Nov 2026 and **fixed the same day in commit `5ef03ed`**):

| ID | Finding | Fix |
|---|---|---|
| D1 | Metro rides said "Wait N min for the first bus" | The wording follows the mode of the first ride (Metro train, bus, other), in all four languages. Browser check: no "first bus" on a Metro journey |
| D2 | The feature list reported fares as available, although the public service never shows a fare | Fares are reported available only when a fare will be shown; otherwise "No verified fares" |
| D3 | Saved routes kept on the server are lost when the free server restarts or wakes | The server reports that its storage is temporary, and the saved-routes panel says so and points to what stays on the phone. A permanent database (H1) removes the cause |
| D4 | The description and opening screen mentioned bus routes and timetables | The description, install text and opening tagline now describe Metro journeys and transport information only |

## 5. Privacy (DPDP Act, 2023 and DPDP Rules, 2025)
The DPDP Rules were notified in November 2025. Most obligations of data fiduciaries apply 18 months later (May 2027).
The application is designed to meet them before any pilot. **No legal review has been done yet.**

| Requirement | Status | Notes |
|---|---|---|
| Collect only what is needed | MET | No names, phone numbers, email, payment data, contacts, photos, analytics or advertising identifiers |
| Notice in clear language | PARTIAL | Draft privacy policy in `docs/government/PRIVACY_POLICY.md`, not yet legally reviewed or translated |
| Consent for location | MET | Asked by the browser only when the passenger taps "Stops near me"; used once; never stored or sent with an identity |
| Erasure | MET | "Delete my data" removes server records and resets the device key |
| Retention | PARTIAL | Device data until deleted; a pilot retention period must be agreed (`docs/government/DATA_RETENTION_POLICY.md`) |
| Grievance contact | OPEN | Must be named before a pilot |
| Breach response | OPEN | A written incident procedure is needed (notice to the Data Protection Board and affected people; CERT-In reporting) |
| Children | MET for the pilot design | Pilot participants are adults only |
| Processors and transfers | AUTHORITY | Hosting is in Singapore today; map images come from OpenStreetMap's servers. The authority may require hosting in India |
| Accounts | N/A today | If enabled, they hold an email or username and a password hash, with export and deletion |

## 6. Government requirements that may apply
These apply if the authority hosts, adopts or co-brands the service. **They are listed here so the authority can
decide; none is claimed as met.**

| Requirement | Applies when | Status |
|---|---|---|
| GIGW 3.0: accessibility at WCAG 2.1 AA | Government website or app | Automated scans: 0 violations on 15 screens in 2 themes. No manual or screen-reader audit yet |
| GIGW 3.0, guideline 5.3.1: security audit and clearance by NIC, STQC or a CERT-In-empanelled auditor before production hosting | Hosting for or by a government body | Not started; to be quoted |
| CERT-In Directions (28 April 2022): report incidents within 6 hours; keep system logs for 180 days in India; synchronise clocks with NIC or NPL time servers | Organisations the Directions cover | AUTHORITY. **Conflict to resolve:** the app keeps no access log by design, for privacy. A pilot may need minimal, time-limited logs |
| Hosting in India, possibly on a MeitY-empanelled cloud | If the authority requires it | AUTHORITY |

## 7. Accessibility
| Check | Status |
|---|---|
| Automated WCAG 2.1 AA scan (axe-core), 15 screens in light and dark themes | MET: 0 violations |
| Keyboard use, visible focus, skip link | MET (browser checks) |
| Large text, dark mode, reduced motion | MET |
| Every screen at 390 px without sideways scrolling | MET |
| Phones from 320 px to 430 px, a tablet and desktops (10 widths, 11 screens each) | MET: no sideways scrolling (`tests/browser/responsive_check.py`, 22 of 22, 18 Nov 2026) |
| Notches and rounded corners (iPhone landscape) | Safe-area padding added; not yet seen on a real iPhone |
| Screen readers (TalkBack, NVDA, VoiceOver) | OPEN: not tested |
| Kannada, Telugu and Hindi reviewed by native speakers | OPEN: first drafts only; 629 texts in each language |

## 8. Reliability
| Check | Status |
|---|---|
| Health check (`/api/health`) used by the host | MET |
| Automated tests on every change (GitHub Actions: Python 3.12 and 3.13, container, PostgreSQL) | MET: 4 of 4 jobs passed on `a97beae` |
| Data survives a restart on PostgreSQL | MET in CI; **not on the public service** (H1) |
| Backups and a restore drill | PARTIAL: SQLite backup tool with integrity check and restore drill; no hosted database backups yet |
| Always-on service | OPEN: the free plan sleeps; first request can take up to a minute |
| Uptime monitoring and an incident runbook | OPEN |

## 9. Data governance
| Control | Status |
|---|---|
| Every timetable belongs to a recorded source with publisher, licence and kind | MET |
| Only an OFFICIAL source can be marked "Officially verified", and only after an administrator records evidence | MET (tests; demo verification refused) |
| Community data is always labelled "Unverified feed", with approximate times and no fares | MET |
| Invented demonstration data is never served by the public service | MET (tests; public check) |
| The community Metro file is pinned by SHA-256 and its licence (ODbL) is credited | MET |
| Upcoming-transport changes need a reason and are kept in a public history and the audit log | MET |
| Removal of an operator's data on request | MET by design: delete the source; the app shows "unavailable" instead |
| Register of sources and licences | MET: [09](09_DATA_SOURCE_AND_LICENCE_REGISTER.md) |
