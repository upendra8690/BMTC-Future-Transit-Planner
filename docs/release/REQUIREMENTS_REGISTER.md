# Master requirements register: Bengaluru Transit Planner 4.0

Prepared on 18 November 2026 against branch `v4`, commit `a97beae`.

**Approval status of every row: none.** No requirement here was supplied, reviewed or approved by BMTC, BMRCL, DULT
or the Government of Karnataka. No written scope, approval, API documentation or acceptance criteria from any of them
exists (see `government_submission_2026/22_APPROVALS_AGREEMENTS_AND_CREDENTIALS.md`). This register is built from the
sources below. When an authority supplies its own requirements, they replace these rows.

| Source code | Source |
|---|---|
| OB | The owner's written briefs of 18 November 2026 |
| NB | Public descriptions of the official Namma BMTC app: press reports and its store listing. **Not verified on a device;** reports disagree about its current features |
| STD | Standards: GTFS and GTFS-Realtime, WCAG 2.1 AA, OWASP ASVS, API Top 10 and MASVS |
| LAW | DPDP Act, 2023 and DPDP Rules, 2025; CERT-In Directions, 2022; GIGW 3.0 if the authority adopts the service |

| Class | Meaning |
|---|---|
| **IV** | Implemented and verified (automated or browser tests, or a check on the public service) |
| **INV** | Implemented but not verified on the target platform |
| **P** | Partially implemented |
| **M** | Missing, and needs no permission to build |
| **GOV** | Requires a government data feed, API or permission. Where the code exists, it is tested only on demonstration data |
| **EXT** | Requires an external provider (payment, SMS, app store, auditor) |
| **DEC** | Requires a decision by the government or the owner |

## Summary (105 requirements, counted from the tables below; updated 19 Nov 2026)
| Class | Count | Share |
|---|---|---|
| IV Implemented and verified | 37 | 35 % |
| INV Implemented, not verified on the target platform | 7 | 7 % |
| P Partially implemented | 13 | 12 % |
| M Missing, buildable without permission | 4 | 4 % |
| GOV Needs government data, API or permission | 28 | 27 % |
| EXT Needs an external provider | 10 | 10 % |
| DEC Needs a government or owner decision | 6 | 6 % |

**What the figures mean:**
- **Verified coverage is 35 %.** 54 % of requirements exist in some form (IV, INV and P together).
- **42 %** cannot be completed by engineering alone (GOV, EXT and DEC).
- **4 %** are missing but can be built now.

Bus information, live transport, ticketing and payments make up most of the blocked share. None of them can become real
without written permission and official data.

## A. Passenger access
Security for every row: scrypt password hashes; sessions stored as hashes; lockout after repeated failures; no account
without PostgreSQL.

| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| A-01 | Registration | OB | Server only (`/api/account/register`); no screen | Accounts off until PostgreSQL exists | `tests/test_accounts.py` (26 tests) | P |
| A-02 | Sign-in and sign-out | OB | Server only | Same | Same | P |
| A-03 | OTP verification | OB | None | SMS provider and TRAI DLT registration; a decision that phone numbers may be collected | — | EXT |
| A-04 | Profile and preferences | OB | Device preferences (language, display); account profile on the server only | Same as A-01 | pytest; e2e | P |
| A-05 | Password recovery | OB | Recovery codes (server) | Same as A-01 | pytest | P |
| A-06 | Account deletion and data export | OB, LAW | Device data: "Delete my data" works. Accounts: server only | Same as A-01 | e2e (device); pytest (accounts) | P |
| A-07 | Privacy settings and notice | OB, LAW | Draft privacy policy; location asked only on tap | Legal review | Document 20, section 5 | P |

## B. Bus information
| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| B-01 | Bus route search | OB, NB | Routes screen and API | Official BMTC GTFS and licence | e2e (demonstration data) | GOV |
| B-02 | Bus stop search | OB, NB | Stops screen and API | Same | e2e (demonstration data) | GOV |
| B-03 | Route numbers and stop lists | OB | Route page | Same | e2e (demonstration data) | GOV |
| B-04 | Route maps | OB, NB | Leaflet map of a route's stops | Same; route paths need `shapes.txt` | e2e (demonstration data) | GOV |
| B-05 | Stop information and departures | OB, NB | Stop page; scheduled departures | Same | e2e (demonstration data) | GOV |
| B-06 | Timetables, first and last trips, CSV | OB | Route and stop pages | Same | Regression (demonstration data) | GOV |
| B-07 | Service status of a route on a date | OB | Classification and date banners | Same | pytest | GOV |
| B-08 | Bus service categories (for example Vajra, Vayu Vajra) | OB, NB | Not shown | Category data from BMTC | — | GOV |
| B-09 | Depot information | OB | None | BMTC data and permission | — | GOV |
| B-10 | Airport bus information | OB | Link to the official airport site | BMTC data | e2e link check | GOV |

## C. Live transport
Security: an official feed's credentials stay in the hosting environment; the feed's own terms apply.

| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| C-01 | Live bus location | OB, NB | Refusing adapter; "unavailable" screen | BMTC real-time agreement (GTFS-Realtime) | pytest; e2e | GOV |
| C-02 | Vehicle tracking on a map | OB, NB | None beyond C-01 | Same | — | GOV |
| C-03 | Estimated arrival times | OB, NB | Scheduled times only, labelled "not live" | Same | pytest | GOV |
| C-04 | Stop-wise arrivals | OB, NB | Scheduled departures per stop | Same, for live arrivals | e2e (demonstration data) | GOV |
| C-05 | Service disruption alerts | OB | None | Official alerts feed; or administrator notices (see E-03) | — | GOV |
| C-06 | Real-time refresh | OB | None | C-01 | — | GOV |
| C-07 | GPS freshness indicator | OB | None | C-01 | — | GOV |

## D. Journey planner
| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| D-01 | Origin and destination with stop search | OB, NB | Plan screen; exact names win | — | Real-mode check 14/14; public deployment check | IV |
| D-02 | Bus-only journeys | OB | Planner `modes=bus` | Official BMTC GTFS | e2e (demonstration data) | GOV |
| D-03 | Metro-only journeys | OB | Planner `modes=metro` | Official BMRCL GTFS for "Officially verified"; today community data, labelled | Public check: Indiranagar to Jayanagar | IV |
| D-04 | Combined bus and Metro journeys | OB, NB | Planner `modes=all` | BMTC and BMRCL GTFS | e2e (demonstration data) | GOV |
| D-05 | Walking connections | OB | Walking transfers between nearby stops | — | e2e (demonstration data); pytest | IV |
| D-06 | Transfers (up to two changes) | OB | Round-based search | — | Public check: changes at Majestic and RV Road | IV |
| D-07 | Journey alternatives, labelled | OB | Options ranked; "Earliest arrival", "Fewest changes" | — | pytest | IV |
| D-08 | Accessible (step-free) journey options | OB | None | Station and stop accessibility data | — | GOV |
| D-09 | Travel-time information | OB | Duration per option and ride; Metro times approximate | — | pytest; public check | IV |
| D-10 | Leave now or choose a date and time | OB | Plan screen | — | e2e | IV |
| D-11 | Correct wording per mode | STD | The wait names the mode of the first ride (Metro train, bus, other) | — | Browser check: no "first bus" on a Metro journey (18 Nov 2026) | IV |
| D-12 | Swap start and destination | OB | Swap button | — | `phase2_check.py` | IV |
| D-13 | Start from my location (nearest stop or station) | OB | Nearest stop or station, never an entrance | Location permission | `phase2_check.py`; regression test | IV |
| D-14 | Share a journey and open a shared journey | OB | Journey links; Web Share, clipboard or on-page link | — | `phase2_check.py` | IV |

## E. Ticketing, passes and notices
Security: no ticket, QR code, receipt or balance is ever produced without a provider; tests enforce this.

| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| E-01 | Digital bus tickets, passes, renewal | OB, NB | Refusing adapters; links to official channels | BMTC ticketing agreement | pytest; e2e | GOV |
| E-02 | Ticket validation, QR codes, receipts, refunds, history | OB | None (deliberately) | BMTC validation infrastructure and rules | pytest proves no QR or receipt is produced | GOV |
| E-03 | Service announcements by administrators (with official source links and end dates) | OB | Service notices on Home; admin editor; official-source allow-list; 31-day limit; audit log | — | `tests/test_notices.py`; `phase2_check.py` | IV |

## F. Payments
Security: never store card numbers or UPI PINs; verify webhooks; idempotent requests; reconcile daily.

| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| F-01 | Approved payment gateway, UPI | OB, NB | Refusing adapter | RBI-authorised payment aggregator; BMTC agreement | pytest | EXT |
| F-02 | Verification, webhooks, idempotency | OB | None | F-01 | — | EXT |
| F-03 | Refunds and reconciliation | OB | None | F-01; BMTC process | — | EXT |
| F-04 | Fraud prevention | OB | None | F-01 | — | EXT |
| F-05 | NCMC | OB | Refusing adapter | Issuing bank and operator | pytest | EXT |

## G. Passenger convenience
| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| G-01 | Favourite stops | OB, NB | Device list | — | e2e | IV |
| G-02 | Saved journeys | OB | Device list; plan again | — | e2e | IV |
| G-03 | Saved routes on the server | OB | Server list per device | Lost on restart on free hosting (D3) | e2e | P |
| G-04 | Recent searches | OB | Device list | — | Code review | INV |
| G-05 | Notifications | OB | Preferences stored (accounts); no delivery | Web push, email or SMS provider; owner decision | pytest | EXT |
| G-06 | Language: English, Kannada, Telugu, Hindi | OB | 629 texts in each | Native-speaker review | pytest (key parity); launch check 268/268 | IV |
| G-07 | Customer support and help | OB | Official websites and helplines listed | Which official channel to use | e2e links | DEC |
| G-08 | Complaints and feedback | OB, NB | None in the app | BMTC decides whether complaints go to its own channel | — | DEC |
| G-09 | Emergency information and dialler | OB | 112, 108, 101, 1098 as phone links (web) | Android: fixed in code, not device-tested | e2e (web) | IV |
| G-10 | Offline use | OB | Service worker: shell and saved timetables | — | e2e offline steps | IV |
| G-11 | Upcoming transport with status labels | OB | Register with sources and history | — | pytest 17; browser 17 | IV |
| G-12 | Rule-based travel assistant | OB | Fixed rules, app data only | — | pytest | IV |
| G-13 | Feature list states only what is true | OB | Fares reported only when shown; temporary server storage reported | — | pytest (`tests/test_client_ip_and_labels.py`) | IV |
| G-14 | Quick destinations | OB | Major Metro stations present in the data, labelled | — | `phase2_check.py` | IV |

## H. Namma Metro
| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| H-01 | Stations (Purple, Green, Yellow) | OB | 83 stations, community data, labelled | Official BMRCL data for "Officially verified" | Public check | IV |
| H-02 | Line information | OB | Lines and stop lists | Same | Real-mode check | IV |
| H-03 | Interchanges | OB | Majestic, RV Road | — | Public check | IV |
| H-04 | Metro schedules | OB | Approximate times, labelled | Official timetables | Public check | IV |
| H-05 | Pink Line | OB | Upcoming transport only | No timetable in any source; owner decision on a station list | — | GOV |
| H-06 | Metro fares | OB | Withheld (estimates only in source) | Official fares and permission | pytest | GOV |
| H-07 | Metro ticketing | OB, NB | Refusing adapter; official link | ONDC registration and BMRCL approval | pytest | GOV |

## I. Data integration
| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| I-01 | GTFS import with validation and limits | STD | Administration and command line | — | pytest | IV |
| I-02 | Verification workflow (only OFFICIAL can be verified) | OB | Yes | — | pytest; e2e | IV |
| I-03 | Feed freshness status | OB | `/api/data-status` | — | Public deployment check | IV |
| I-04 | Scheduled synchronisation from an official source | OB | None | An official source to synchronise from | — | GOV |
| I-05 | GTFS-Realtime ingestion with freshness checks | STD | Adapter interface only | Real-time agreement | — | GOV |
| I-06 | Documented adapter per provider capability | OB | Yes, all refusing | — | pytest | IV |

## J. Administration
| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| J-01 | Administrator sign-in | OB | Shared key; per-person roles built but off | PostgreSQL; owner enables accounts | pytest | P |
| J-02 | Role-based access (passenger, editor, admin) | OB | Server only | Same | pytest | P |
| J-03 | User management | OB | Server only | Same | pytest | P |
| J-04 | Route and stop management | OB | Through GTFS import, not hand editing | The data owner manages its own data | pytest | IV |
| J-05 | Data and API health monitoring | OB | Health and data-status endpoints; no alerting | Monitoring service (free tier) | Public check | P |
| J-06 | Audit log of sensitive actions | OB, LAW | Yes | — | pytest | IV |
| J-07 | Operational reports | OB | Basic statistics | Requirements from the authority | pytest | P |
| J-08 | Ticket monitoring, payment reconciliation | OB | None | E and F | — | GOV |
| J-09 | Complaint management | OB | None | G-08 | — | DEC |
| J-10 | Security alerts | OB | None | Monitoring service | — | M |

## K. Platforms (compatibility in `PHASE1_BASELINE_AND_ROADMAP.md`)
| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| K-01 | Responsive web at 390 px and desktop | OB | Yes | — | Launch check 268/268 | IV |
| K-02 | Responsive web at 320, 360, 375, 412, 430 px, tablet and desktop | OB | Yes | — | `tests/browser/responsive_check.py` 22/22 (11 screens at 10 widths) | IV |
| K-03 | Installable PWA with offline shell | OB | Manifest, icons, service worker | Device install not tested | e2e (Edge) | INV |
| K-04 | Firefox and Safari | OB | Standard web code | Not tested | — | INV |
| K-05 | Android debug APK | OB | Built by CI (compile check) | Not run on a device or emulator | CI `ab94f8a` | INV |
| K-06 | Android signed release APK and AAB | OB | AAB and APK build in CI; release signing switches on when the owner's key is in GitHub secrets | Owner's release key; Google Play account | CI (`d72e5c9`) | DEC |
| K-07 | Android location for "near me" | OB | Asked only when the page asks; never retained | Not run on a device | CI compile and analyze (`d72e5c9`) | INV |
| K-08 | Android load-error retry and downloads | OB | Try again; downloads to the share sheet | Not run on a device | CI compile and analyze (`d72e5c9`) | INV |
| K-09 | Android deep links | OB | None | Domain verification file | — | M |
| K-10 | iPhone and iPad (Safari PWA) | OB | Standard web code; bottom safe area only | Not tested on a device | — | INV |
| K-11 | iOS app project and signing | OB | None | A Mac or a macOS CI runner; Apple Developer Program | — | EXT |

## L. Security, privacy and operations
| ID | Requirement | Source | Built today | Dependency or blocker | Evidence | Class |
|---|---|---|---|---|---|---|
| L-01 | OWASP self-assessment with a findings register | STD | Document 20 | — | 18 Nov 2026 | IV |
| L-02 | Reliable per-visitor rate limiting | STD | Counted by the hosting edge's visitor address (R1 fixed) | — | Live test 18 Nov 2026; pytest | IV |
| L-03 | CSP without inline styles | STD | Inline styles allowed (S4) | — | Code review | P |
| L-04 | Secrets only in the hosting environment | STD | Yes | — | Commit scan | IV |
| L-05 | Dependency and static scans in CI on every push | STD | bandit and pip-audit in the CI test jobs | — | CI `5ef03ed` | IV |
| L-06 | Browser and accessibility tests in CI | STD | Run by hand only | — | — | M |
| L-07 | Permanent database with backups | OB | Proven in CI; not used by the public service | Owner's database | CI PostgreSQL job | DEC |
| L-08 | Incident response procedure | LAW | None | — | — | M |
| L-09 | Logging policy that satisfies CERT-In without recording searches or locations | LAW | No access log | Authority's decision | — | DEC |
| L-10 | Independent security audit | LAW | None | Auditor; authority's requirement | — | EXT |
| L-11 | Screen-reader and native-language review | STD | Automated scans only | Volunteers or reviewers | axe 0 violations | EXT |
