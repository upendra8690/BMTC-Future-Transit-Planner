# Namma Metro timetable: community reconstruction (bmrcl-gtfs)

`bmrcl-gtfs-f402c4c.zip` is an **unofficial** GTFS feed for the Namma Metro Purple, Green and Yellow lines. It was
made by the community project [bmrcl-gtfs](https://github.com/Vonter/bmrcl-gtfs). It is used here unmodified.

| Item | Value |
|---|---|
| Source | https://github.com/Vonter/bmrcl-gtfs, file `gtfs/bmrcl.zip` at commit `f402c4c69a5d314320024f84620fa83e909c4188` (17 Aug 2026, "Update Yellow Line timetable as of 17th August 2026") |
| SHA-256 | `c19f56f32ad53525c71191125409dc8dded12dd2cebfc576ad9a4db23a62b8a7` (checked by `scripts/load_community_metro.py` before every import) |
| Licence | Open Database License (ODbL) 1.0, https://opendatacommons.org/licenses/odbl/1-0/ |
| Contains | OpenStreetMap data, © OpenStreetMap contributors (station locations, line shapes) |
| Timetable source | The timetables BMRCL publishes on https://www.bmrc.co.in/metro-timings/, transcribed by the project |
| Valid | 17 Aug 2026 to 17 Aug 2027 (`feed_info.txt`) |
| Contents | Purple 37 stations, Green 32, Yellow 16; 3,279 trips; weekday, Monday, Sunday and holiday calendars |

**Attribution.** Contains information from bmrcl-gtfs, which is made available under the Open Database License
(ODbL). Contains OpenStreetMap data © OpenStreetMap contributors. Timetable information originally published by
Bengaluru Metro Rail Corporation Limited.

## How the app treats it, and why
The project's README states three things that the app takes into account:
- **Intermediate-station times are approximations.** BMRCL publishes no times for intermediate stations; the
  project estimates them from stop spacing, dwell time and average speed, so they may be "a couple of minutes" off.
  The app marks every ride from this feed **"Approximate times"**.
- **Fares are estimated by the project's build script.** The app **never shows them as prices**. The journey shows
  "Fare: not shown, because this source's fares are not verified".
- **Short-loop trains may be missing.**

The app also:
- **Imports it as kind `COMMUNITY`.** Its classification is therefore always "Unverified feed". It can never be
  verified as official, because only an `OFFICIAL` source can be.
- **Names the real publisher.** The feed's own `feed_info.txt` names BMRCL as publisher, but BMRCL did not publish
  this file. The app's source record names the community project as publisher.
- **Leaves out the elevated Pink Line.** It opened on 14 Nov 2026 per press reports and is not in this version.

## Why the BMTC community feed is not used
The same author publishes `bmtc-gtfs`, also under ODbL. It is built from the Namma BMTC app's own data interface, which
is not a published API. The project owner decided not to use feeds derived from the operator's app, so it is not
included.

## Updating
1. Download a newer `gtfs/bmrcl.zip` from the project at a specific commit.
2. Check its `feed_info.txt` dates and line station counts.
3. Replace the file, then update `FEED`, `SHA256` and `SOURCE_URL` in `scripts/load_community_metro.py` and this README.

Never edit the file itself. ODbL share-alike applies to the feed and anything derived from it, and this folder keeps
it available under ODbL.
