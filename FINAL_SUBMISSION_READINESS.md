# Final submission readiness: 18 November 2026

> **Later update on 18 November 2026.** Current figures are in `government_submission_2026/10_TEST_AND_PERFORMANCE_EVIDENCE.md`
> (pytest 501 passed on `a97beae`; all 14 deployment checks passed). Open findings found after this report, including
> R1 and D1 to D4, are in `government_submission_2026/20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md`. The audit and
> roadmap are in `docs/release/PHASE1_BASELINE_AND_ROADMAP.md`. Where this file differs, the newer files apply.

## Recommendation: **READY FOR GOVERNMENT TECHNICAL REVIEW**
This means ready to be **reviewed**, as an unofficial prototype. It does **not** mean government-approved, ready for
a pilot, or ready for production.
- **Official data:** none.
- **Metro:** real Namma Metro information from an unofficial community source, with approximate times.
- **Missing:** real BMTC bus data, live information and accounts.
- **Android:** not tested on a phone.

Before anything is sent (checklist 19, section A), the owner must:
1. Fill in contact details and signatures.
2. Confirm each addressee by telephone.
3. Decide on a code licence, or keep the wording "publicly available".
4. Re-run `scripts/verify_deployment.py` on the public address on the day.

## 1. Commit and branch
- **Branch:** `v4` of github.com/upendra8690/BMTC-Future-Transit-Planner-3.0. It is worked on in a full clone whose
  `origin` is that repository.
- **`main` (3.0):** not changed, and nothing was merged.
- **Earlier pushed commits:** `ab94f8a` (submission package), `93a98f6` (separate service, editable upcoming
  transport).
- **This report:** belongs to the commit after `93a98f6`. Run `git log -1 origin/v4` for its hash.

## 2. Public deployment
| Service | Address | Verified on 18 Nov 2026 |
|---|---|---|
| 4.0, separate Render service `bengaluru-transit-planner-v4`, branch `v4` | https://bengaluru-transit-planner-v4.onrender.com | Before this commit, every check of `scripts/verify_deployment.py` passed: HTTPS, health 200, version 4.0.0-beta.1, the 4.0 page, CSP and HSTS, upcoming transport. After this commit deploys, the same script must be run again; see the chat report for the result |
| 3.0 (unchanged) | https://bmtc-future-transit-planner-3-0.onrender.com | Health 200 (after a 22 s cold start); still 3.0 (no `/api/features`); title "BMTC Future Transit Planner" |

On the free plan, a service sleeps after inactivity. The first request then takes up to a minute, and the disk is
erased on every restart.

## 3. Real information and demonstration data are now separate
- **The public service runs in real mode** (`DEMO_MODE=0`, the default). It never serves the invented demo feeds, even
  if one is loaded; missing real data is never filled with invented data.
- **A demonstration server** (`DEMO_MODE=1`) serves them and shows a banner on every screen. It is for development and
  presentations only.
- Tests: `tests/test_demo_mode.py`, `tests/browser/real_mode_check.py`, and the CI real-mode container.

## 4. Real data in the public service
| Data | Source | Status |
|---|---|---|
| Namma Metro Purple (37 stations), Green (32), Yellow (16): stations, lines, interchanges, timetables | bmrcl-gtfs community project, reconstructed from BMRCL's published timetables and OpenStreetMap; ODbL; valid 17 Aug 2026 – 17 Aug 2027; pinned by SHA-256 | **Real but unofficial.** Always "Unverified feed"; times marked "Approximate"; fares never shown; elevated Pink Line missing |
| Upcoming transport (7 entries) | Press and secondary sources, each linked and dated | Administrators update them without code changes |
| Emergency numbers, official websites | Public numbers; operators' own sites | All links checked |
| Maps | OpenStreetMap tiles | Attribution shown |
| **BMTC bus routes, stops, timetables, fares** | **None** | No lawful, authorised source found. The community BMTC feed is built from the Namma BMTC app's data interface, so it is not used |

## 5. Integrations that need government or provider permission
| Integration | Needs | Status |
|---|---|---|
| Official BMTC and BMRCL schedules (GTFS) | Data licence from DULT or the operators | Not requested (letters 15–17 drafted) |
| Live tracking, arrival estimates, alerts | BMTC real-time data agreement | AWAITING AUTHORISATION |
| Bus tickets and passes | BMTC ticketing agreement | AWAITING AUTHORISATION |
| Metro QR tickets | ONDC registration and BMRCL approval | AWAITING AUTHORISATION |
| Payments, wallet | A licensed payment aggregator | AWAITING AUTHORISATION |
| NCMC | An issuing bank and the operator | AWAITING AUTHORISATION |

## 6. Android
- **3.0 APK.** `app-latest` blocks telephone and official links, including SOS 112. This is fixed on `v4`; porting the
  fix to `main` needs approval.
- **4.0 APK.** The 4.0 shell compiles: the CI compile check passed for `ab94f8a`. No 4.0 APK has been published,
  signed or tested on a phone. A push cannot publish one (`tests/test_release_guard.py`).

## 7. Exact test results (final code, 18 Nov 2026)
| Suite | Result |
|---|---|
| ruff | All checks passed |
| pytest | **470 passed, 5 skipped, 0 failed** (the skips need the DejaVu Sans font) |
| bandit (application and new scripts) | No issues |
| pip-audit | No known vulnerabilities |
| Browser regression, 3.0 + 4.0 (demonstration server) | 121 passed, 0 failed |
| Launch screens, 4 languages, phone and desktop | 268 / 268 |
| End-to-end crawl and journey (demonstration server) | 1,028 / 1,028; 869 controls, 0 decorative or broken |
| Real-mode screens (public configuration) | 14 / 14 |
| Upcoming-transport editor | 17 / 17 |
| Accessibility (axe, WCAG 2.1 AA) | 0 violations, 15 screens × 2 themes |
| Security probes | 34 passed, 0 failed |
| Deployment checker, local real and demonstration servers | Every application check passes; HTTPS and HSTS need the public address |

## 8. Defects found and fixed this round
- **A typed station name could match a different station.** "Jayanagar" also matched "Vijayanagar", and the planner
  answered with a trip to Vijayanagar. Exact names now win; partial names still find every match. Tests prove the
  old behaviour fails.
- **Each Metro station appeared twice,** once per platform. Platforms are now merged.
- **Earlier this day:** the admin editor's field named `id` hid the form's own id, so saving reloaded the page.

## 9. Security, privacy, data
- **No high-severity finding.** Open items:
  - S5, medium: one shared admin key;
  - H1, medium: no persistent database or backups on free hosting;
  - A1, medium: Android not tested on a phone;
  - S4, low: inline styles in the content security policy.
- **No independent penetration test.**
- **Privacy:** no names, contacts, locations, searches or payment data are stored, and device keys are hashed.
- **Database:** SQLite on an ephemeral disk. Saved routes and upcoming-transport edits are lost on restart.
  PostgreSQL is supported and proven in CI: migrations, the real data import, and a saved route, an admin change and
  an account all surviving a restart. Using it needs the owner's database (`docs/launch/POSTGRESQL_PRODUCTION.md`).

## 10. Not built yet, and why
| Feature | Why not yet |
|---|---|
| Passenger accounts, recovery codes, account-saved journeys, editor and admin roles | **Built and tested (26 tests; CI persistence on PostgreSQL), switched off.** They start only with `ACCOUNTS_ENABLED=1` on PostgreSQL. The account screens are the next step once the database exists (`docs/launch/ACCOUNTS_AND_ROLES.md`) |
| Notifications | Preferences are stored; sending needs a delivery service (web push, email or SMS) |
| Service alerts | No authorised alerts feed. Administrator-managed notices would be the next step |
| AI (language-model) assistant | Needs an API key and a cost budget from the owner. The current assistant follows fixed rules and uses only the app's data |
| Hospitals, toilets, water, parking, EV charging, station facilities | No verified, licensed dataset chosen yet |
| BMTC bus information | No authorised source |

## 11. Suitability
| Use | Suitable? | Why |
|---|---|---|
| Internal testing | **Yes** | All suites pass |
| Public demonstration | **Yes**: the public service in real mode; a demonstration server for the demo journeys | Real and invented data are separate and labelled |
| Government technical review | **Yes**, after the pre-send actions above | Complete package, honest limitations, reproducible evidence |
| Limited pilot | **Can be proposed; not ready to start** | Needs a data licence, persistent hosting, phone testing and a privacy review |
| Production passenger use | **No** | No official data, no bus data, no live data, no accounts, free hosting |
