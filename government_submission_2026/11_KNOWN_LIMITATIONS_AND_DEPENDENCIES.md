# 11 Known limitations and dependencies

## Limitations
| # | Limitation | Effect on passengers | What removes it |
|---|---|---|---|
| 1 | **No official data.** The Namma Metro timetable comes from an unofficial community reconstruction (approximate times, no fares, no Pink Line); there is no real BMTC bus data at all | Metro journeys are indicative only; bus journeys are not possible | A written licence for BMTC and BMRCL GTFS (requests 15–17) |
| 2 | **No live information.** No vehicle positions, arrival predictions or service alerts | Only scheduled times, always labelled "not live" | A BMTC real-time data agreement (GTFS-Realtime) |
| 3 | **No tickets, passes, Metro QR, payments, wallet or NCMC** | Passengers are pointed to the official channels | Written agreements with the operator, ONDC, a payment aggregator and a bank |
| 4 | **No passenger accounts in use.** They are built and tested, but switched off until a permanent database exists | Saved items belong to one device | PostgreSQL (`DATABASE_URL`), then `ACCOUNTS_ENABLED=1` and the account screens |
| 5 | **Free hosting.** The server sleeps when idle, taking up to a minute to wake, and its disk is wiped on restart | Slow first load; saved routes on the server can be lost | Paid always-on hosting and PostgreSQL with backups |
| 6 | **Open findings from 18 Nov 2026:** the rate limit can be bypassed behind the hosting proxy (R1); Metro rides say "first bus" (D1); the feature list overstates fares and server-saved routes (D2, D3); descriptions mention bus data that the public service lacks (D4) | Minor confusion; a possible brief refusal of service | Fixes designed; they await the applicant's approval of the code changes ([20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md)) |
| 7 | **The Android app has not been tested on a phone or emulator.** Calls, official links and the back button were fixed in code only. The release build is signed with a debug key, and no Play bundle (AAB) exists | Unknown behaviour on real devices | Emulator and phone tests; a release key held by the applicant |
| 8 | **Android "Stops near me".** The WebView shell does not grant location | Inside the Android app, search by stop name instead | Location support in the shell |
| 9 | **Translations not reviewed** by native speakers | Wording may be unnatural | Review by native speakers |
| 10 | **No screen-reader test.** Only automated WCAG scans so far | Problems that tools cannot detect may remain | TalkBack and NVDA testing with users |
| 11 | **No passenger services data**: hospitals, toilets, drinking water, parking, EV charging, station facilities | Not shown | Licensed civic or operator datasets |
| 12 | **The travel assistant follows fixed rules,** not AI, and understands English only | Limited questions | Further development; it never invents an answer |
| 13 | **No independent security test** | Self-assessment only | Review by the authority's security team or an empanelled auditor |
| 14 | **No open-source licence chosen.** The code is public but default copyright applies | Others may not legally reuse the code | The owner chooses a licence (for example MIT or Apache-2.0) |
| 15 | **One developer** | Limited support capacity | Clear scope for any pilot; public issue tracking |

## Dependencies
| Dependency | Used for | Cost today | Risk |
|---|---|---|---|
| DULT, BMTC, BMRCL data permission | All real timetables and fares | — | Without it the app stays a demonstration |
| Render (hosting) | 3.0 demo; the separate 4.0 service | Free tier | Sleeps when idle; disk not persistent |
| PostgreSQL, for example Neon | Persistent data for a pilot | Free tier available | Not set up yet |
| GitHub and GitHub Actions | Source code, tests, Android builds | Free | — |
| OpenStreetMap tiles | Maps | Free, light use only | Heavy use needs another tile source |
| Python packages (FastAPI, SQLAlchemy and others) | Server | Free, open source | Checked with pip-audit: no known vulnerabilities |
| Leaflet 1.9.4 (bundled) | Maps in the app | Free (BSD 2-Clause) | — |
| Flutter and Android SDK (in CI only) | Android wrapper | Free | Signed only with a debug key today; Play Store release needs a release key and a developer account |
