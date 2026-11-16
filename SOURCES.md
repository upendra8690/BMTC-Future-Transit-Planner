# Data sources

Research date: 15 November 2026. The searches used news reports, public dataset listings and third-party pages. The
official portal itself could not be opened from the build environment, so nothing below is confirmed from the source.

## What this build contains

- **No official BMTC timetable, route, stop or fare data is loaded.** Nothing was downloaded from any official source.
- **No BMTC route, stop, fare or future schedule was typed in or invented.** No timetable file is shipped. The synthetic
  demo feed is generated on request by `backend/app/gtfs/synthetic.py`, or by `scripts/make_synthetic_gtfs.py`. It is
  labelled `SYNTHETIC_DEMO` and classified `UNVERIFIED_FEED`. Its route names, such as `DEMO-1`, are not BMTC route numbers.
- **No third-party feed is bundled in this package.** The community feeds below were reviewed and not used.
- **No Namma Metro data is included, and no metro feed was loaded or tested.** The planner has no metro-specific logic.
  It stores each feed's route type and shows it in route listings, but it does not use it when it plans a journey. A
  metro feed would need its own source record, its own check of the publisher's terms, and the same import and
  verification steps as a bus feed. The dashboard footer and the `/api/meta` response both carry a notice that names
  BMTC, BMRCL and Namma Metro and says the planner is not affiliated with them.

## Official candidate: not verified

| Item | What was found | Status |
|---|---|---|
| Publisher | Bengaluru Metropolitan Transport Corporation (BMTC), with Bangalore Metro Rail Corporation (BMRCL), publishing schedule data in GTFS format. | Reported in press coverage in 2024 and 2025. |
| Portal | The Directorate of Urban Land Transport (DULT) hosts the data on its Transport Data Hub, `https://tdh.dult-karnataka.com`. | The address appears in press coverage. The build sandbox cannot reach it (the host is not on the allowlist), so the feed, its date range and its download link were not checked. |
| Scope | BMTC said it would publish static schedule data first and real-time GTFS later. | Real-time data is out of scope for this build. |
| Licence and terms | No licence statement for the hub's data was found. | **Unknown.** Read the portal's own terms before redistributing any BMTC data. |

Conflicting statement: an OpenStreetMap wiki talk page says there is no official GTFS dataset from BMTC. Its date is
not shown. The later press reports above describe an official portal, so the wiki page is probably out of date. This
conflict is not resolved here.

## Community feeds and references reviewed and not used

| Feed or reference | Why it was not used |
|---|---|
| `github.com/Vonter/bmtc-gtfs` | Its README calls it an unofficial dataset. The raw data was taken from the Namma BMTC app, so its origin and terms are not clear. The Mobility Database lists it as a community feed (`mdb-2595`). |
| TUMI / TUMIdata "GTFS: Karnataka - Bangalore" (2024 record) | The file name points to a 2013 dataset. The licence is recorded as "not specified", and the page says the licence may be out of date. |
| Older public feeds (for example, a Plasma timetable provider page) | They claim validity only up to 2020, so they cannot describe current or future service. |
| `github.com/iotakodali/bmtc-realtime-api` | Real-time estimates are out of scope. Its code and data are under CC BY-NC-SA 4.0, which does not allow commercial use. |
| `open-bmtc` 2.0 (a project supplied with the request) | Supplied with the request as a reference. Excluded because it describes an unofficial, reverse-engineered BMTC API with no licence and no affiliation with BMTC or Chalo. No code or data from it is in this package. |

## Third-party code shipped with the planner

| Component | Licence | Where |
|---|---|---|
| Leaflet 1.9.4 | BSD 2-Clause | `dashboard/vendor/leaflet/`, with its licence file. Served to the browser. |
| axe-core 4.14.0 | Mozilla Public License 2.0 | `tests/browser/vendor/axe-core/`, with its licence file. Used only by the browser checks, and not served to users. |

## How data enters the planner

1. An administrator creates a data source and gives it a kind: `OFFICIAL`, `COMMUNITY`, `SYNTHETIC_DEMO` or `UNKNOWN`.
2. A GTFS ZIP is imported, through the Administration page or `scripts/import_gtfs.py`. Imports from a source that is
   not verified are shown as `UNVERIFIED_FEED`.
3. Only a source of kind `OFFICIAL` can be verified. Verifying needs a non-empty note. The message asks for the evidence (the publisher's page,
   the date it was checked and the licence). The server does not check what the note says. Revoking needs no note. Verification is the only route to `OFFICIAL_VERIFIED`.
4. Fare files (`fare_attributes.txt` and `fare_rules.txt`) are stored with the feed when the feed includes them. The
   planner prices a one-ride journey only from the fare rules that name its route, or that name no route, and that have
   no origin, destination or contains zone. Fare rules with a zone are stored but never used for a price, and a journey
   with changes is never given a total.

## Before any release that includes official data

1. Open `https://tdh.dult-karnataka.com` from an ordinary internet connection. Record the feed's download address, its
   publication date, its service date range and the licence text, with the date you checked.
2. Import the file as an `OFFICIAL` source with the publisher's address as the source URL.
3. Check the import's report (warnings and errors), the fare count in the report, and the coverage shown for each year.
4. Verify the source with a note that says where and when it was checked.
5. Update this file with the record from step 1.

Until those steps are done, the planner reports that no officially verified timetable is available for 2027 to 2030.
