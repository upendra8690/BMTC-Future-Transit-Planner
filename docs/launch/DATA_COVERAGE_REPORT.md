# Data coverage report: Bengaluru Transit Planner 4.0

Checked on 18 November 2026. This report states what the **public service** shows (real mode, `DEMO_MODE=0`). Invented
demonstration data is never part of it.

| Label | Meaning |
|---|---|
| **REAL, OFFICIAL** | Published by the operator or authority, licensed for this use, and verified in the app. |
| **REAL, UNVERIFIED** | Describes real services, but comes from a non-official source; labelled in the app. |
| **MISSING** | No usable source exists today. |
| **RESTRICTED** | Exists, but needs written permission, an agreement or credentials. |

## 1. Coverage at a glance
| Information | Status | Source | Notes |
|---|---|---|---|
| Namma Metro Purple, Green, Yellow: stations, lines, interchanges | **REAL, UNVERIFIED** | bmrcl-gtfs community feed (ODbL) | 83 stations (85 line-station pairs); interchanges Majestic (Purple/Green) and RV Road (Green/Yellow) |
| Namma Metro timetables, first and last trains | **REAL, UNVERIFIED** | Same feed, from BMRCL's published timetables | Valid 17 Aug 2026 – 17 Aug 2027. Intermediate-station times are approximate and labelled so |
| Namma Metro Pink Line, elevated section | **MISSING** | — | Opened 14 Nov 2026 per press reports, after the feed's last update (17 Aug 2026). Shown only in Upcoming transport |
| Namma Metro fares | **MISSING** (estimates withheld) | The feed's fares were estimated by its build script | Never shown as prices: "Fare: not shown, because this source's fares are not verified" |
| Namma Metro station facilities, accessibility, lifts | **MISSING** | — | Not in any source used |
| BMTC bus routes, stops, timetables, fares | **MISSING** for the public service | See section 3 | No authorised source; community sources are derived from the operator's app |
| BMTC and BMRCL official GTFS | **RESTRICTED** | DULT Transport Data Hub (reported in 2024) | The reported address does not resolve; letters 15–17 ask for access and terms |
| Live vehicle positions, arrival predictions, service alerts | **RESTRICTED** | BMTC (and BMRCL) | Need a data-sharing agreement; the app says "Live vehicle information is currently unavailable" |
| Tickets, passes, Metro QR, payments, NCMC | **RESTRICTED** | Operators, ONDC, payment aggregators, banks | Need agreements; links go to official channels |
| Upcoming transport (7 projects) | **REAL, UNVERIFIED** | Press and secondary sources, each linked and dated | Administrators update it; no official expected-start date is shown, because none comes from an official announcement |
| Emergency numbers, official websites | **REAL** | Public numbers; the organisations' own sites | All links opened with status 200 on 17 Nov 2026 |
| Map background | **REAL** | OpenStreetMap tiles (ODbL) | Light use under the tile usage policy |
| Hospitals, toilets, water, parking, EV charging | **MISSING** | — | No licensed dataset chosen |

## 2. Audit of the community Namma Metro feed
| Check | Result |
|---|---|
| Source and version | `Vonter/bmrcl-gtfs`, file `gtfs/bmrcl.zip` at commit `f402c4c` (17 Aug 2026), pinned by SHA-256 `c19f56f3…62b8a7`. This is still the newest upstream version on 18 Nov 2026 |
| Licence | ODbL 1.0 (the repository's LICENSE file). Attribution is in the app, in `reference_data/namma_metro_community/README.md` and in the feed's own `attributions.txt` (producer: the community author; operator and authority: BMRCL) |
| Publisher shown | The feed's `feed_info.txt` names BMRCL as publisher, which is misleading for an unofficial file. The app records the community project as publisher and never marks the feed official |
| Validation | gtfs-validator 7.0.0 (upstream report): **0 errors**, 8 warnings, all "stop too far from shape" (geometry only; no effect on journeys) |
| Our own import | Imported without rejection; checked by `tests/test_demo_mode.py` and the CI PostgreSQL job |
| Station coverage | Purple 37 (Whitefield (Kadugodi) – Challaghatta), Green 32 (Madavara – Silk Institute), Yellow 16 (RV Road – Delta Electronics Bommasandra). Matches the published line lengths |
| Calendar | Weekday, Monday, Sunday and holiday services; 64 holiday or exception dates; valid 17 Aug 2026 – 17 Aug 2027 |
| Service hours in the feed | First departures: Monday 04:15 (Yellow 05:05), other weekdays 05:00 (Yellow 06:00), Sunday 07:00. Last arrivals 00:00 to 00:28 |
| Accuracy limits (from the project) | Intermediate-station times are estimated from spacing and speed ("a couple of minutes" off); some short-loop trains may be missing; fares are estimates |
| Freshness | Yellow Line timetable as of 17 Aug 2026; the other lines as last transcribed by the project (June–July 2026). Not cross-checked by this project against BMRCL's current timings |
| **Missing Pink Line (elevated)** | Six stations, per press reports: Kalena Agrahara, Hulimavu, Bilekahalli (IIM Bangalore), N.S. Palya – J.P. Nagar 4th Phase, Jayadeva Hospital (interchange with Yellow) and S.G. Palya (formerly Tavarekere). Names vary between reports. Journeys to or from these stations are not possible until a feed includes them |

## 3. Publicly available BMTC datasets
**Access limit.** data.opencity.in refused every automated request on 18 Nov 2026 (HTTP 403, including through a
standard page reader), so the pages could not be read directly. The facts below come from search-engine summaries of
those pages. **The owner should confirm them in a normal browser before any decision.**

| Dataset | What it holds | Licence (as summarised) | Provenance | Usable for the public service? |
|---|---|---|---|---|
| OpenCity "BMTC Stops with Location and Routes" (CSV, about 1.9 MB, updated 25 Nov 2025; an older copy 4 Nov 2022) | Stops with latitude and longitude, the routes serving each stop, trip counts. **No timetables** | CC BY-SA 2.0, credited to Sathya Sankaran | Source listed as `bmtc.vonter.top/bus_stops_accessibility/`, the same author as bmtc-gtfs, built from the Namma BMTC app's data | **Not used**, by the owner's decision on app-derived data. The licence would allow reuse with attribution and share-alike, so the owner could choose differently; see section 5 |
| OpenCity per-ward KML and CSV files ("Stops and routes map for division …") | The same stops by ward; trip counts | Varies; some "No License Provided" | Converted by OpenCity from the dataset above | Not used (same provenance; some unlicensed) |
| OpenCity "BMTC Bus stops Locations" (about 9,600 stops; updated 27 Feb 2026; year of data unknown) | Stop locations only | Not confirmed | Not confirmed | **Not used**: licence and provenance unverified |
| OpenCity "Bengaluru Public Transport Infrastructure" (2010–2016 files, Big-10 routes 2012, depots) | Historical stops, routes, depots | Varies; some unlicensed | BMTC-era releases and others | **Not used**: out of date; current service must not be shown from historical data |
| bmtc-gtfs (Vonter, ODbL; listed in the Mobility Database as a community feed) | Full GTFS: routes, stops, timetables | ODbL | "Raw data sourced from Namma BMTC app" (its README) | **Not used**, by the owner's decision |
| TUMI Data Hub "GTFS Bengaluru" (2013 file name, updated 2024) | Old GTFS | Not specified | Individual author | Not used: old and unlicensed |

## 4. Authorised official routes to real data
| Data | Who decides | What to ask for | Status |
|---|---|---|---|
| BMTC and BMRCL static GTFS | DULT (Transport Data Hub) or each operator | The current download address, registration process, licence or terms, permitted use in a free public app, attribution wording, update frequency | Letter 17 (DULT) drafted; the 2024 address `tdh.dult-karnataka.com` does not resolve |
| BMTC GTFS directly | BMTC (Managing Director; IT/ITS officer) | Static GTFS, licence, and whether GTFS-Realtime (vehicle positions, trip updates, alerts) is shared, and under what agreement | Letter 15 drafted |
| BMRCL GTFS including the Pink Line | BMRCL (project office) | Station, line, timetable and fare data with terms; Pink Line timetable | Letter 16 drafted |
| Ticketing and QR | BMTC; BMRCL through ONDC | The approved integration route; not sought now | Out of scope until data is settled |

## 5. Decisions only the owner can make
1. **Send letter 17 (DULT) first.** It is the one route that could give official, verified bus and Metro data.
2. **Whether to use the OpenCity stops dataset (CC BY-SA 2.0).** It would add real BMTC stop locations and route
   lists, but no timetables, labelled "unverified community data". Its provenance is the Namma BMTC app, which your
   earlier decision excludes. The app is ready to label such data honestly, but will not use it without your decision.
3. **Whether to show the elevated Pink Line stations without a timetable**, as a list only. Today they appear only in
   Upcoming transport, because no timetable exists in any source used.
