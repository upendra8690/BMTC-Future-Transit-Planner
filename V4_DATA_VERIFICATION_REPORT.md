# V4 data verification report — 17 November 2026

## Verdict
**No real, verified transport data is loaded.** Every timetable, route, stop, station, fare and journey in the app
comes from two synthetic demonstration feeds. They are invented for this project, named "Demo …", and labelled as
such everywhere. No licence has been obtained from BMTC, BMRCL or DULT, and no request has been sent.

## What is loaded
| Feed | Agency | Kind | Classification | Covers | Contents |
|---|---|---|---|---|---|
| `demo_feed.zip` | Demo Transit (SYNTHETIC) | SYNTHETIC_DEMO | Unverified feed | 1 Jun 2026 – 31 Dec 2027 | Bus routes DEMO-1, DEMO-2 (route type 3); six demo stops; demo fares |
| `demo_metro_feed.zip` | Demo Metro (SYNTHETIC) | SYNTHETIC_DEMO | Unverified feed | 1 Jun 2026 – 31 Dec 2027 | Metro line DEMO-M1 (route type 1); four demo stations |

Official classification: **empty**. `GET /api/routes?classification=OFFICIAL_VERIFIED` returns no routes, and a
journey for an official date answers "No officially verified timetable is available".

## Real-world information the app shows (not timetables)
| Information | Source | Checked |
|---|---|---|
| Emergency numbers 112, 108, 101, 1098 and railway enquiry 139 | Public emergency and helpline numbers; ERSS website | 16 Nov 2026 |
| Official websites (BMTC, BMRCL, DULT, Indian Railways, airport, traffic police, tourism) | Each site's own address | **17 Nov 2026: all open with status 200 in Edge** |
| Upcoming transport (7 projects) | Press and Wikipedia, linked on each entry | 17 Nov 2026; all 9 source links open with status 200 |

### Upcoming-transport statuses and how sure we are
| Project | Status shown | Basis | Confidence |
|---|---|---|---|
| Yellow Line | Operating since Aug 2025 | Wikipedia | Secondary source |
| Pink Line, elevated | Operating since 14 Nov 2026 | Deccan Herald, Oneindia (around the opening) | Press; confirm on BMRCL's site |
| Pink Line, underground | Under construction (2027) | Wikipedia | Dates differ between sources |
| Blue Line | Under construction | Wikipedia | Dates conflict |
| Suburban rail, Mallige line | Under construction | Wikipedia | Project deadline reported as 2030 |
| BMTC Pink Line feeders (5 routes) | Operating since 14 Nov 2026 | Deccan Herald | Press; timetables not loaded |
| 200 mini AC electric feeder buses | Announced (Sept 2026) | Channel IAM | Announcement only |

A validator (pytest) rejects any entry shown as Operating without an opening date on or before the date it was
checked, and the planner never uses these entries.

## Checks that demo data cannot pass as official
See the table in [V4_SECURITY_REPORT.md](V4_SECURITY_REPORT.md). All six checks pass.

## What is needed for "Working with verified data"
1. A written licence or terms for BMTC and BMRCL GTFS (DULT Transport Data Hub, or the operators directly).
2. Import the feed through Administration as kind OFFICIAL, with its source URL and licence.
3. An administrator verifies it against the publisher's source, with evidence. Only then does it show as
   "Officially verified".
