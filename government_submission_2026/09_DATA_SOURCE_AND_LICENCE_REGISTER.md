# 09 Data source, licence and integration register

Checked on 17 November 2026. The live copy is served by the application at `GET /api/providers` and
`GET /api/integrations`, and appears on its "Data and providers" screen.

**Today no official data is loaded and no provider is connected. No permission has been requested and no credentials
exist.**
- **Private interfaces.** The application uses no private or reverse-engineered interface.
- **Real data from a community feed.** One openly licensed community feed is used: the Namma Metro timetable
  reconstructed by the bmrcl-gtfs project from BMRCL's published timetables and OpenStreetMap (ODbL, row 14). It is
  labelled unverified, its times are marked approximate, and its fares are never shown.
- **Feeds not used.** Community feeds built from an operator's app (such as bmtc-gtfs, from the Namma BMTC app's data
  interface) are not used.

## Summary
| # | Organisation | Data or API | Permission | Credentials | Implementation |
|---|---|---|---|---|---|
| 1 | DULT, for BMTC | Static bus schedules (GTFS), via the Transport Data Hub | Not requested | None | GTFS import ready; nothing loaded |
| 2 | DULT, for BMRCL | Static Metro schedules (GTFS), via the Transport Data Hub | Not requested | None | GTFS import ready; nothing loaded |
| 3 | BMTC | Static GTFS directly from BMTC, if not via DULT | Not requested | None | GTFS import ready |
| 4 | BMTC | Real-time data: vehicle positions, trip updates, alerts (GTFS-Realtime) | Not requested | None | Adapter refuses (503 `NO_AUTHORISED_LIVE_FEED`) |
| 5 | BMTC | Digital tickets and passes | Not requested | None | Adapters refuse (503 `NEEDS_TICKETING_AGREEMENT`) |
| 6 | BMRCL | Stations, timetables and fares | Not requested | None | GTFS import ready |
| 7 | BMRCL with ONDC | Metro QR tickets | Not requested | None | Adapter refuses (503 `NEEDS_ONDC_REGISTRATION`) |
| 8 | An RBI-authorised payment aggregator | UPI, cards, wallet | No provider chosen | None | Adapter refuses (503 `NEEDS_PAYMENT_GATEWAY`) |
| 9 | An issuing bank, with the operator | NCMC card services | Not requested | None | Adapter refuses (503 `NEEDS_BANK_INTEGRATION`) |
| 10 | OpenStreetMap Foundation | Map tiles | Not needed (public tile policy) | None needed | Connected, with attribution |
| 11 | Official websites and public numbers | Links only: BMTC, BMRCL, DULT, Indian Railways, airport, traffic police, tourism, ERSS 112 | Not needed for links | — | Connected; all 18 links opened with status 200 on 17 Nov 2026 |
| 12 | This project | Invented demonstration feeds | Not needed | — | Served only by a demonstration server (DEMO_MODE=1), never by the public service; labelled SYNTHETIC everywhere |
| 13 | Press and secondary sources | Status of upcoming projects (no timetables) | Not needed (cited, not copied) | — | Connected; each entry links its source and check date |
| 14 | bmrcl-gtfs community project (unofficial) | Namma Metro Purple, Green, Yellow: stations and reconstructed timetables, valid 17 Aug 2026 to 17 Aug 2027 | Not needed (ODbL 1.0, with attribution) | None needed | Connected as kind COMMUNITY ("Unverified feed"); approximate times; fares never shown; file pinned by SHA-256 (`reference_data/namma_metro_community/`) |
| 15 | bmtc-gtfs community project | BMTC routes and timetables | ODbL, but built from the Namma BMTC app's data interface | — | **Not used**, by the owner's decision: derived from an operator's app |
| 16 | OpenCity (data.opencity.in) BMTC stop datasets | Stops with locations, routes and trip counts (no timetables); older 2010–2016 files | One CC BY-SA 2.0 (derived from the same app data); others unlicensed or unconfirmed | — | **Not used.** The site refused automated access, so details come from search summaries; see `docs/launch/DATA_COVERAGE_REPORT.md` |

## Details
### 1–2. DULT Transport Data Hub: BMTC and BMRCL static GTFS
| Field | Entry |
|---|---|
| Official organisation | Directorate of Urban Land Transport (DULT), Urban Development Department, Government of Karnataka |
| Official source | Press reports from 2024 say BMTC and BMRCL publish GTFS on a DULT-run Transport Data Hub at `tdh.dult-karnataka.com`. **On 17 Nov 2026 that address did not resolve from our test machine.** We found no link to it on the DULT home page (dult.karnataka.gov.in) |
| Licence and usage conditions | **Not found.** The DULT website's policy asks for permission before its content is reused |
| Access permission | Not requested. Requested in letter [17](17_DULT_TECHNICAL_REVIEW_REQUEST.md) (not sent) |
| Credentials | None held |
| Implementation | Administration → import GTFS (validates, records source URL and licence) → verify against the publisher, with evidence → shown as "Officially verified" |
| Testing evidence | The import, validation and verification flow is tested on demo feeds (pytest, regression, e2e). It has never been run on official data |
| Update frequency | Unknown; to be agreed with DULT |
| Outstanding | Current address of the hub, the licence or terms, permission to use the data in a free public app, and an attribution wording |

### 3–5. BMTC
| Field | Entry |
|---|---|
| Official organisation | Bengaluru Metropolitan Transport Corporation, Central Offices, K.H. Road, Shanthinagar, Bengaluru 560027 |
| Official source | mybmtc.karnataka.gov.in. The website links a public Metro-feeder tracking page, but it has no API terms and **is not used** |
| Licence | No reuse licence found for schedules or real-time data |
| Permission | Not requested. Requested in letter [15](15_BMTC_DATA_ACCESS_REQUEST.md) (not sent) |
| Credentials | None |
| Implementation | Static GTFS through the standard import. Real-time data will come through the `live_vehicles` adapter as GTFS-Realtime, after an agreement. Tickets and passes need a formal ticketing agreement |
| Testing evidence | pytest and e2e prove that every adapter refuses and that no ticket or vehicle position can be produced |
| Update frequency | Static: on each timetable change. Real-time: seconds |
| Outstanding | Data licence; real-time data-sharing terms; the ticketing integration process |

### 6–7. BMRCL
| Field | Entry |
|---|---|
| Official organisation | Bangalore Metro Rail Corporation Limited, 3rd Floor, BMTC Complex, K.H. Road, Shanthinagar, Bengaluru 560027 (the office the BMRCL website lists for project-related matters) |
| Official source | english.bmrc.co.in, which also gives a passenger channel (travelhelp@bmrc.co.in; toll-free 1800-425-12345) that is **not** for data requests |
| Licence | No reuse licence found |
| Permission | Not requested. Requested in letter [16](16_BMRCL_DATA_ACCESS_REQUEST.md) (not sent) |
| Credentials | None |
| Implementation | Static GTFS through the standard import. QR tickets only through the approved route (ONDC) with BMRCL approval |
| Testing evidence | Metro planning tested on the demo Metro feed (e2e step 5); the QR adapter refuses (pytest, e2e) |
| Update frequency | On each timetable or fare change |
| Outstanding | Data and fare licence; confirmation of the approved ticketing route |

### 8–9. Payments and NCMC
No provider has been approached. These need an RBI-authorised payment aggregator, merchant onboarding and the
operator's consent; NCMC also needs an issuing bank. **The application never accepts or stores card, UPI or bank
details,** and it never shows a payment as successful.

### 10. OpenStreetMap
| Field | Entry |
|---|---|
| Licence | Data under the Open Database Licence (ODbL), with attribution; tiles under the OSM tile usage policy (light use) |
| Implementation | Map credit links to openstreetmap.org/copyright |
| Outstanding | For a pilot with heavy use, a commercial tile provider or a self-hosted tile server |

### 12. Demonstration feeds
| Feed | Agency | Covers | Content |
|---|---|---|---|
| `demo_feed.zip` | Demo Transit (SYNTHETIC) | 1 Jun 2026 – 31 Dec 2027 | Bus routes DEMO-1 and DEMO-2, six demo stops, demo fares |
| `demo_metro_feed.zip` | Demo Metro (SYNTHETIC) | 1 Jun 2026 – 31 Dec 2027 | Metro line DEMO-M1, four demo stations |

These feeds are kind `SYNTHETIC_DEMO`, so they can never be verified as official.

### 13. Upcoming-transport sources (status information only)
These entries are kept in the database. Administrators update them without code changes; each change needs a
reason and appears in the entry's public history. An expected start date is accepted only from an official
announcement, so none of the entries below shows one.

| Project | Status shown | Source | Confidence |
|---|---|---|---|
| Yellow Line | Operating since Aug 2025 | Wikipedia | Secondary |
| Pink Line, elevated | Operating since 14 Nov 2026 | Deccan Herald; Oneindia | Press; to confirm with BMRCL |
| Pink Line, underground | Under construction; no official opening date shown | Wikipedia | Reported 2027 targets differ, so they appear only in a note |
| Blue Line, including the airport section | Under construction | Wikipedia | Dates conflict |
| Suburban rail, Mallige line | Under construction | Wikipedia | Deadline reported as 2030 |
| BMTC Pink Line feeder routes (5) | Operating since 14 Nov 2026 | Deccan Herald | Press; no timetables loaded |
| 200 mini AC electric feeder buses | Announced (Sept 2026) | Channel IAM | Announcement only |

We would replace these with the operators' own announcements if the authority prefers.
