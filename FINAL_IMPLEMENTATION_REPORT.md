# Final implementation report: Bengaluru Transit Planner 4.0 (18 November 2026)

Branch `v4`; public service https://bengaluru-transit-planner-v4.onrender.com, which runs in **real mode** and never
shows invented data; 3.0 on `main` is unchanged.

**Not complete, and not official.**
- No official BMTC or BMRCL data is loaded and no operator has approved anything.
- The Namma Metro data is real but unofficial.
- There is no BMTC bus data.
- Passenger accounts are built but stay off until a permanent database exists.

Details: [data coverage](docs/launch/DATA_COVERAGE_REPORT.md), [database](docs/launch/POSTGRESQL_PRODUCTION.md),
[accounts](docs/launch/ACCOUNTS_AND_ROLES.md), [readiness](FINAL_SUBMISSION_READINESS.md).

## 1. Done in this round, with evidence
| Item | Evidence |
|---|---|
| PostgreSQL works: driver (psycopg 3.2), hosting addresses accepted, migrations, real data import, database check | CI job "PostgreSQL" on PostgreSQL 16, passing |
| Data survives a restart on PostgreSQL: saved route, admin change, passenger account and its saved journey | `scripts/check_persistence.py` in the same CI job |
| Accounts, sessions, password change and recovery, export, deletion; saved journeys per account; notification preferences | `tests/test_accounts.py`, 26 tests |
| Roles (passenger, editor, admin): a signed-in editor or admin is named in the audit log | Same tests |
| **Safe by default:** accounts refuse to run without PostgreSQL; the public service shows "Accounts: needs a permanent database" | Tests for the off state and the refusal |
| Fixed: the feature list could report bus routes as available on a real-mode server that still held a demo feed | Catalogue now uses the same real/demo filter as every other query |
| Fixed: a `postgres://` database address was not recognised as PostgreSQL when deciding whether accounts may run | Test case added |
| Data coverage audit: OpenCity datasets, official access routes, community Metro feed, the missing Pink Line | `docs/launch/DATA_COVERAGE_REPORT.md` |

## 2. Next work that needs no outside permission (in priority order)
| # | Item | Effort | Blocked by |
|---|---|---|---|
| 1 | **Account screens in the app** (sign-in, register, saved journeys, notification choices, delete and export) in four languages | Medium | Nothing technical, but useful only once the database exists (owner step 1 below). Build them then, so they can be tested on the real database |
| 2 | **Administrator service notices**: short notices with an official source link and an end date, hidden automatically when expired | Small–medium | None |
| 3 | **Remove inline styles** so the content security policy can drop `style-src 'unsafe-inline'` (finding S4) | Small | None |
| 4 | **Pink Line elevated stations** shown as a station list without times | Small | Your decision (section 3, item 4) |
| 5 | **Translation review** of Kannada, Telugu and Hindi, including this round's new texts | — | Native-speaker volunteers |
| 6 | **Phone tests:** TalkBack, installing the web app, and the Android shell's calls, links and back button | — | A phone; for the 3.0 APK fix, your approval |

## 3. Needs your action (credentials, money, decisions)
| # | Action | Why | Cost |
|---|---|---|---|
| 1 | **Create Render Postgres** (Basic-256mb, Singapore) and set `DATABASE_URL` on the 4.0 service yourself; never share the address | Makes all saved data permanent; prerequisite for accounts | About US$6 a month (confirm on Render's pricing page) |
| 2 | After step 1, check persistence (`docs/launch/POSTGRESQL_PRODUCTION.md`, step 4), then set `ACCOUNTS_ENABLED=1` if you want accounts | Accounts start only on PostgreSQL | ₹0 |
| 3 | **Send letter 17 to DULT** (then 15 BMTC, 16 BMRCL) after adding your contact details and confirming addressees by phone | The only route to official, verified bus and Metro data, including the Pink Line | Postage |
| 4 | **Decide on the OpenCity stops dataset** (CC BY-SA 2.0, derived from the Namma BMTC app) | It would add real BMTC stop locations and route lists, but no times, labelled unverified. Your earlier rule excludes app-derived data | ₹0 |
| 5 | **Choose a code licence**, or keep "publicly available" | Legal decision | ₹0 |
| 6 | **Approve porting the Android shell fix to `main`** | The 3.0 APK cannot call 112 or open official sites | ₹0 |
| 7 | Optional: Render Starter for the web service | Removes the free plan's sleep (up to a minute to wake; 3.0 took about 12 minutes once) | About US$7 a month |
| 8 | Optional: choose a notification channel (web push, email or SMS) | Delivery needs a provider | Varies |

## 4. Needs a written agreement from an operator or provider
- Official BMTC and BMRCL timetables and fares.
- Live vehicle positions, arrival predictions and service alerts.
- Bus tickets and passes.
- Metro QR tickets (through ONDC).
- Payments and wallet.
- NCMC.

The app keeps each one switched off, with the official channel shown.

## 5. Test results on this round's final code
See the chat report and `government_submission_2026/10_TEST_AND_PERFORMANCE_EVIDENCE.md`. Previous round, for
reference: public site real-mode browser check 14/14; deployment checks 12/12. No test was removed or weakened.
