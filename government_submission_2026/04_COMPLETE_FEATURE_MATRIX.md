# 04 Complete feature matrix

Version 4.0.0-beta.1 on branch `v4`, checked 17 to 18 November 2026. Nothing has been added to this matrix to make it
look complete. Features that do not exist are marked NOT IMPLEMENTED.

| Status | Meaning |
|---|---|
| **PASS** | Implemented and tested end to end. Does not depend on official data. |
| **DEMO ONLY** | Implemented and tested, but only on the invented demonstration data. Becomes real when licensed data is loaded. |
| **PARTIAL** | Some of the feature works, and the note says which part. |
| **AWAITING AUTHORISATION** | Needs written permission or an agreement from an operator or provider. Until then the app refuses with a clear message. |
| **BLOCKED** | Held up by a missing environment, device or account, not by permission. |
| **FAIL** | Tested and broken. There are none at present. |
| **NOT IMPLEMENTED** | Does not exist in the application. |

Column key:
- **FE** is the screen.
- **BE** is the server endpoint or service.
- **DB** is stored data.
- **Data** is where the content comes from.
- **Evidence** names the suite in [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md).

## A. BMTC bus
| Feature | FE | BE | DB | Data | Status | Evidence and notes |
|---|---|---|---|---|---|---|
| Route search | Routes | `/api/routes` | GTFS tables | Demo feed | DEMO ONLY | e2e forms: results and "no match" message |
| Stop search | Stops | `/api/stops` | GTFS tables | Demo feed | DEMO ONLY | e2e forms |
| Route details and stop list | Route page | route API | GTFS tables | Demo feed | DEMO ONLY | e2e step 4; each stop opens its own page |
| Timetables, first and last trips, CSV | Route and stop pages | timetable API | GTFS tables | Demo feed | DEMO ONLY | Regression: 66 trips on 1 Jan 2027 |
| Fares | Journey results | GTFS fare rules | GTFS tables | Invented demo fares | DEMO ONLY | Only shown when the feed has fare rules; never estimated |
| Journey planner | Plan | `/api/plan` | GTFS tables | Demo feed | DEMO ONLY | e2e steps 2–6; pytest |
| Interchanges (up to two changes) | Plan | `/api/plan` | — | Demo feed | DEMO ONLY | e2e: "no changes" is sent and respected |
| Nearby stops | Nearby | stops API | — | Demo feed; location only when the user taps | DEMO ONLY | Regression; e2e "location refused" message. Not available inside the Android shell (see F) |
| Maps | All map views | — | — | OpenStreetMap tiles | PASS | e2e: zoom works; credit to OpenStreetMap |
| Airport services | Home and More: official airport site | — | — | Official link | PARTIAL | Link works. Airport bus (Vayu Vajra) timetables need BMTC data |
| Service alerts | — | — | — | No authorised alerts feed | NOT IMPLEMENTED | No screen; would need GTFS-Realtime alerts from BMTC |
| Saved routes | Favourites | saved-routes API | Server, under a hashed device key | User | PASS | e2e: stored and listed after refresh; another device cannot read them |
| Saved journeys | Favourites | — | On the device | User | PASS | e2e steps 7, 9, 10: save, plan again, refresh, offline |

## B. Namma Metro
| Feature | FE | BE | DB | Data | Status | Evidence and notes |
|---|---|---|---|---|---|---|
| Lines | Metro | routes API (Metro type) | GTFS tables | Demo Metro feed | DEMO ONLY | e2e |
| Stations and station search | Metro | stops API | GTFS tables | Demo Metro feed | DEMO ONLY | e2e forms |
| Metro-to-Metro interchange | Plan | `/api/plan` | — | Demo Metro feed | PARTIAL | The planner handles transfers, but the demo feed has one Metro line, so a line-to-line change cannot be shown |
| Metro journey planning | Plan, "Metro only" | `/api/plan?modes=metro` | — | Demo Metro feed | DEMO ONLY | e2e step 5 (Demo Metro Central to Demo Metro Tech Park) |
| Bus + Metro journeys | Plan | `/api/plan` | — | Both demo feeds | DEMO ONLY | e2e step 6: bus, walk, Metro |
| Station facilities | — | — | — | No licensed dataset | NOT IMPLEMENTED | |
| Ticketing links | Tickets, Metro | — | — | Official BMRCL website link | PASS | Points to official channels; sells nothing |

## C. Capabilities comparable to the operators' own apps
This application is not, and does not imitate, the official Namma BMTC or Namma Metro apps.

| Feature | FE | BE | Status | Evidence and notes |
|---|---|---|---|---|
| Live vehicle tracking | Live (explains) | `live_vehicles` adapter returns 503 | AWAITING AUTHORISATION | pytest, e2e. Needs a BMTC data-sharing agreement |
| Arrival estimates | Live (explains) | same | AWAITING AUTHORISATION | Only scheduled times are shown, always labelled "not live" |
| Digital bus tickets | Tickets (explains) | `bus_tickets` returns 503 | AWAITING AUTHORISATION | No ticket ever produced |
| Bus passes | Tickets | `bus_passes` returns 503 | AWAITING AUTHORISATION | |
| Metro QR tickets | Tickets, Metro | `metro_qr_tickets` returns 503 | AWAITING AUTHORISATION | Needs ONDC registration and BMRCL approval; no QR code ever drawn |
| Payments | — | `payments` returns 503 | AWAITING AUTHORISATION | Needs a licensed payment aggregator; no card or UPI data is accepted or stored |
| Wallet | — | part of `payments` | AWAITING AUTHORISATION | No balance is ever shown |
| Ticket history | — | — | NOT IMPLEMENTED | There are no tickets to record |
| NCMC information | Tickets: explanatory card | `ncmc` returns 503 | PARTIAL | Explains that banks issue and recharge NCMC cards; no card services |

## D. Future transport (status information only; never used to plan journeys)
| Feature | Status | Evidence and notes |
|---|---|---|
| Metro extensions (Yellow, Pink elevated and underground, Blue) | PASS | Upcoming screen: status, dates and sources for each; validator test rejects "operating" without an opening date; all source links open |
| Suburban rail (Mallige line) | PASS | Status and sources |
| New bus routes and feeder services | PARTIAL | The five BMTC Pink Line feeder routes appear as a status entry (press source); there are no timetables |
| Electric buses | PARTIAL | One "announced" entry (200 mini AC electric feeder buses); no fleet data |
| New stations | PARTIAL | Status is per line section, not per station |
| Airport and railway connections | PARTIAL | Blue Line airport section status; links to the airport and Indian Railways; railway enquiry 139. No timetables |
| Future integrated scenarios, 2027–2030 | PASS | Scenarios and Compare screens, carried over from 3.0; labelled as this project's estimates, not official forecasts |

## E. Passenger services
| Feature | Status | Evidence and notes |
|---|---|---|
| Emergency numbers 112, 108, 101, 1098 and railway enquiry 139 | PASS | e2e: valid `tel:` links; the numbers are public |
| SOS "Call 112" | PASS in browsers; see F for Android | Opens the phone dialler; the app is not an emergency service |
| Police and traffic | PASS | 112 and the Bengaluru Traffic Police official website |
| Hospitals (list or map) | NOT IMPLEMENTED | Only the 108 ambulance number |
| Public toilets, drinking water, parking, EV charging | NOT IMPLEMENTED | No licensed dataset; the catalogue lists it as "planned, needs licensed data" |
| Accessibility information for stops and stations | NOT IMPLEMENTED | No data on step-free access |
| Tourism and public facilities | PARTIAL | Link to the official Karnataka Tourism website only |

## F. Platform
| Feature | Status | Evidence and notes |
|---|---|---|
| English, Kannada, Telugu, Hindi | PASS | e2e steps 8–9; pytest enforces that every key exists in all four. Not reviewed by native speakers |
| Passenger accounts and authentication | NOT IMPLEMENTED | Guest use only. A PostgreSQL account design is planned |
| Administrator authentication | PASS | Secret key, constant-time comparison; wrong key refused (probes, e2e) |
| Saved journeys | PASS | See A |
| Notifications | NOT IMPLEMENTED | |
| Installable web app (PWA) | PASS | Chromium's installability check reports no errors. Not yet installed on a real phone |
| Offline use | PASS | e2e step 10: shell and saved journeys open offline; planning shows an error with Retry |
| Android app | BLOCKED | Not compiled on the test machine (no Flutter SDK). A compile-only check runs in GitHub Actions; its result is in `FINAL_SUBMISSION_READINESS.md`. Not installed on a phone. Calls, official links and the back button were fixed in code. "Stops near me" cannot get a location inside the shell |
| Accessibility of the app | PASS (automated) | axe: no violations on 15 screens in both themes. No screen-reader test yet |
| Large text, dark mode, low-data mode | PASS | e2e: each switch changes the display |
| Privacy: "Delete my data" | PASS | e2e: server records, device lists and device key all removed |
| Administration: GTFS import, validation, verification, backup | PASS | Regression and e2e. Only sources of kind OFFICIAL can be verified; the demo source is refused |
| Travel assistant | DEMO ONLY | Rule-based, not AI; English questions only; answers come from the timetable API; refuses live, ticket and payment questions |
| Every control does something | PASS | e2e: 321 of 321 controls on 20 screens produced an effect |

## Totals
| Status | Count of rows above |
|---|---|
| PASS | 20 |
| DEMO ONLY | 13 |
| PARTIAL | 8 |
| AWAITING AUTHORISATION | 7 |
| BLOCKED | 1 |
| FAIL | 0 |
| NOT IMPLEMENTED | 8 |
