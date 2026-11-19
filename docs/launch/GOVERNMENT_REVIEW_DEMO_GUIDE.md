# Demonstration guide for reviewers (about 10 minutes)

**Say first:** "This is an independent, unofficial app. It is not approved by, or affiliated with, BMTC, BMRCL or the
Government of Karnataka. Today it runs on invented demonstration data, because we have not yet received permission to
use official timetables."

Open the 4.0 staging URL on a phone. If it has been idle, allow about a minute for the free server to wake.

| Step | Screen | Do | Point out |
|---|---|---|---|
| 1 | Home | Show the search box, map and tiles | One app for bus and Metro; four languages (switch to Kannada) |
| 2 | Plan a journey | Choose "Unverified feed". From "Demo Lake View" to "Demo Metro Hub", travel by "Bus and Metro" | A bus ride, a walk to the station, a Metro ride; each ride names its data source; times are scheduled, not live |
| 3 | Plan a journey | Same trip with "Bus only", then "Metro only" | The mode filter; the app says clearly when no journey exists |
| 4 | Travel assistant | Tap "Demo Lake View to Demo Metro Hub", then "When will my bus arrive?" | Answers come from the timetable; it refuses to invent arrival times |
| 5 | Namma Metro | Show lines and stations | Station search and links to the official ticketing channels |
| 6 | Upcoming transport | Scroll the list | Every entry has a status, sources and a check date; proposed services are never shown as running |
| 7 | Live tracking, then Tickets | Open each | Clearly unavailable until an authorised feed or agreement exists; links to official channels |
| 8 | Data and providers | Open | Demo-only banner; licence and permission status of every source; which integrations wait for which agreement |
| 9 | My account | "Delete my data" | Privacy: no name, phone or email collected; erasure on request |
| 10 | More services | SOS | Calls 112 through the phone dialler; the app is not an emergency service |

## What we are asking for
1. Technical feedback.
2. Guidance on the process to request licensed GTFS data (DULT Transport Data Hub, BMTC, BMRCL).

We are not asking for procurement, funding or endorsement.

## Questions to expect
- *Is any of this official data?* No. All data shown is invented for the demonstration and labelled as such.
- *Can it show live buses?* Not without an authorised feed. The screen and adapter are ready; the feature stays off
  until then.
- *Does it sell tickets?* No, and it will not without a written agreement.
- *Where is user data stored?* Only a hashed device key and the items a person saves. Searches and locations are not
  stored. See `docs/government/PRIVACY_POLICY.md` (a draft).
