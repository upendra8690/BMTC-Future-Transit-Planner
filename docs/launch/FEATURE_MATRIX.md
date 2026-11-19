# Feature matrix — 4.0.0-beta.1 (17 November 2026)

Statuses: **Working and tested** · **Working with verified data** · **Demo only** · **Awaiting provider access** ·
**Planned** · **Blocked** · **Not implemented**.

"Demo only" means the code works and is tested, but the only data loaded is the project's invented SYNTHETIC demo
feed. No feature is "Working with verified data", because no licensed official dataset is loaded.

## A. Bus services
| Feature | Status | Notes |
|---|---|---|
| Search routes by number, name, destination | Demo only | |
| Search stops by name | Demo only | |
| Nearby stops (location on tap only) | Demo only | Location is used once and not stored |
| Route details and full stop sequence | Demo only | |
| Timetables, first and last trips | Demo only | The timetable lists every trip of the day |
| Fares | Demo only | Shown only from fare rules in the loaded feed, with its classification |
| Route maps | Demo only | OpenStreetMap tiles |
| Direct and interchange journeys | Demo only | Up to two changes, walking transfers |
| Airport services (Vayu Vajra) | Awaiting provider access | No BMTC data; the official airport link is shown |
| Service alerts and disruptions | Not implemented | No authorised alerts feed exists to show |
| Saved stops and saved routes | Working and tested | Stops in the browser; routes on the server under a device key |
| Favourite whole journeys | Not implemented | |
| Bus tracking screen | Awaiting provider access | The screen explains why and links to official channels |
| Bus ETA | Awaiting provider access | Never estimated or invented |

## B. Namma BMTC 2.0 capability areas
| Area | Status |
|---|---|
| Real-time tracking; stop-wise arrivals; nearby buses | Awaiting provider access |
| Route timetables; journey planning; bus + Metro planning | Demo only |
| Digital bus tickets; passes; active tickets and receipts | Awaiting provider access (adapter refuses with 503) |
| Metro QR tickets | Awaiting provider access (ONDC registration and BMRCL approval) |
| Wallet, payment history, UPI | Awaiting provider access (no payments are taken) |
| NCMC information | Working and tested (information card and official links) |
| NCMC transactions | Awaiting provider access |

## C. Namma Metro
| Feature | Status |
|---|---|
| Lines, stations, station search | Demo only |
| Interchanges and station-to-station planning | Demo only |
| Bus to Metro and Metro to bus | Demo only |
| Metro route maps | Demo only |
| Verified fares and operating hours | Awaiting provider access |
| First and last train | Demo only (from the loaded timetable) |
| Station facilities and accessibility | Not implemented |
| Official ticketing and smart-card links | Working and tested |

## D. Unified journey planner
| Feature | Status |
|---|---|
| Bus only / Metro only / bus + Metro choice | Demo only (new `modes` filter; tested) |
| Walking connections, multiple interchanges | Demo only |
| Stops, walking distance, changes, total time, alternatives | Demo only |
| Fare only from fare data in the feed | Demo only |
| Source and classification on every ride | Working and tested |
| "Bus + Metro" label on mixed journeys | Working and tested |

## E. Upcoming transport
| Feature | Status |
|---|---|
| Registry with Operating / Announced / Under construction / Planned / Awaiting confirmation / Unavailable | Working and tested |
| Source, announcement date and check date on every entry | Working and tested |
| Validator that rejects a future service marked as operating | Working and tested |
| Timetables for new lines and feeders | Awaiting provider access |

## F. Facilities and city services
| Feature | Status |
|---|---|
| Emergency numbers (112, 108, 101, 1098) and official links | Working and tested |
| Hospitals, police stations, toilets, water, parking, EV charging, accessibility facilities, hotels, restaurants, public offices | Planned (needs a properly licensed dataset; nothing is invented) |
| Railway and airport connections | Official links only |

## G. Accounts and personalisation
| Feature | Status |
|---|---|
| Registration, login, profile | Not implemented (planned with Neon Postgres) |
| Saved routes and stops; recent searches; preferences; language | Working and tested (per device) |
| Notification preferences | Not implemented |
| Privacy controls: "Delete my data" | Working and tested |

## H. Travel assistant
| Feature | Status |
|---|---|
| Assistant | Working and tested. It is rule-based, not an AI model, and understands English questions only. Answers come from the planner, route, stop and Metro endpoints (demo data). It refuses live arrivals, tickets and payments, and gives 112 for emergencies |

## I and J. Languages, mobile, accessibility
| Feature | Status |
|---|---|
| English, Kannada, Telugu, Hindi on every screen | Working and tested (key parity enforced). Not professionally reviewed |
| Responsive layout | Working and tested (390 px and 1280 px) |
| PWA: manifest, service worker, offline reading of saved items | Working and tested in a browser; install not tested on a device |
| Low-data mode, dark mode, large text | Working and tested |
| Keyboard and screen-reader support | Automated WCAG 2.1 AA scan clean; not tested with a real screen reader |
| Android shell | Built for 3.0; the 4.0 build is blocked until the public URL exists |

## Other
| Feature | Status |
|---|---|
| Admin: data sources, verification, GTFS upload, backups, audit log | Working and tested (shared admin key) |
| Future scenarios 2027–2030 (3.0 feature) | Working and tested; labelled estimates |
| Notifications | Not implemented |
