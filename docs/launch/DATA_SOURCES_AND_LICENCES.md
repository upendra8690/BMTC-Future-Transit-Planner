# Data sources and licences (provider registry)

The live copy of this registry is served by the app at `GET /api/providers` and shown on the "Data and providers"
screen. The source is `backend/app/services/registry.py`. Checked 17 November 2026.

| Provider | Dataset / API | URL | Licence and terms | Permission | Owner | Update frequency | Last successful update | Integration | Known limitations |
|---|---|---|---|---|---|---|---|---|---|
| DULT, Government of Karnataka | BMTC and BMRCL static GTFS (Transport Data Hub) | dult.karnataka.gov.in | Not found; the website policy requires prior permission to republish | Not requested (draft letter, not sent) | DULT / BMTC / BMRCL | Unknown | Never | Not connected | No DULT data loaded |
| BMTC | Routes, stops, timetables, fares | mybmtc.karnataka.gov.in | Not published for reuse | Not requested | BMTC | Unknown | Never | Not connected | No BMTC data loaded |
| BMTC | Live positions and arrival predictions | mybmtc.karnataka.gov.in | Agreement only | Not requested | BMTC | Real time | Never | Blocked | Live screens explain the gap |
| BMTC | Tickets and passes | mybmtc.karnataka.gov.in | Ticketing agreement | Not requested | BMTC | — | — | Blocked | No tickets issued |
| BMRCL | Stations, timetables, fares | english.bmrc.co.in | Website content; reuse needs permission | Not requested | BMRCL | Unknown | Never | Not connected | No BMRCL data loaded |
| BMRCL via ONDC apps | Metro QR tickets | english.bmrc.co.in | ONDC registration and BMRCL approval | Not requested | BMRCL | — | — | Blocked | No QR codes shown |
| Licensed payment aggregator | UPI, cards, wallet, NCMC | — | Merchant and operator agreements | Not requested | — | — | — | Blocked | No payments; no card or UPI data stored |
| OpenStreetMap Foundation | Map tiles | openstreetmap.org/copyright | ODbL data; tile usage policy | Not needed | OSM contributors | Continuous | (service) | Connected | Light use only |
| This project | SYNTHETIC demo bus and Metro feeds | — | Project's own invented data | Not needed | This project | On deployment | Shown live in the app | Connected | Never a real service; cannot be marked official |

## How demo data is kept separate from official data
- **Database:** every feed belongs to a data source with a `kind`. A source can be verified, and its feeds classified
  `OFFICIAL_VERIFIED`, only when `kind = OFFICIAL` (`backend/app/services/verification.py`). Demo sources are
  `SYNTHETIC_DEMO`, so their feeds are always `UNVERIFIED_FEED`.
- **API:** every timetable request takes a `classification`. The default is `OFFICIAL_VERIFIED`, which returns
  nothing today. `GET /api/data-status` reports `demo_only: true` while only demo feeds are loaded.
- **Interface:** every result carries a classification badge, and the "Data and providers" screen shows a demo-only
  banner.

## Upcoming-transport sources (status information only, not timetables)
| Project | Status | Source |
|---|---|---|
| Yellow Line, RV Road to Bommasandra | Operating (opened Aug 2025) | Wikipedia |
| Pink Line, elevated section | Operating (opened to the public 14 Nov 2026 per press reports) | Deccan Herald; Oneindia |
| Pink Line, underground section | Under construction (2027; dates differ) | Wikipedia |
| Blue Line, Silk Board to KR Puram to airport | Under construction (dates conflict) | Wikipedia |
| Suburban rail, Mallige line | Under construction (project deadline reported as March 2030) | Wikipedia |
| BMTC Pink Line feeder routes (5) | Operating from 14 Nov 2026 per press report | Deccan Herald |
| BMTC 200 mini AC electric feeder buses | Announced (Sept 2026) | Channel IAM |

These are press and secondary sources; each entry says so and asks the reader to confirm on the operator's site.
