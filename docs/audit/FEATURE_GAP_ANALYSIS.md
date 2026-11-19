# Feature gap analysis against Namma BMTC 2.0

**Source for the official app:** screenshots of Namma BMTC 2.0 supplied by the owner on 19 November 2026 (its Google
Play listing, publisher Bengaluru Metropolitan Transport Corporation, and four in-app screens). Features not visible
in those screenshots are not assumed. This app is independent and is not a replacement for the official app.

Status labels are defined in [AUDIT.md](AUDIT.md).

## Feature by feature
| Namma BMTC 2.0 (as seen) | This app | Status here | What closes the gap |
|---|---|---|---|
| "Find and track your bus": bus search | Route and stop search (built) | WAITING FOR OFFICIAL API/PERMISSION (works only on a demonstration server) | Official BMTC GTFS and licence |
| Live arrival times at a stop ("In 6 min" with a live icon) | Scheduled departures only, labelled "not live" | WAITING FOR OFFICIAL API/PERMISSION | BMTC real-time agreement (GTFS-Realtime) |
| "Near you": map of nearby bus stops with walking time | Nearby stops and stations on a map; Metro stations only; entrances removed in this audit | IMPLEMENTED AND TESTED (Metro); bus stops WAITING FOR OFFICIAL API/PERMISSION | Official BMTC stop data |
| Stop page: next buses with live times | Stop page with scheduled departures | IMPLEMENTED AND TESTED (Metro, scheduled); live WAITING FOR OFFICIAL API/PERMISSION | As above |
| "Plan your journey" (bus and Metro) | Journey planner: Metro journeys with changes; bus and combined journeys | Metro: IMPLEMENTED AND TESTED (unverified community data); bus and combined: DEMONSTRATION ONLY | Official BMTC and BMRCL GTFS |
| Buy a bus and Metro ticket from the journey | Explains that tickets need an agreement; links to official channels | WAITING FOR OFFICIAL API/PERMISSION | BMTC ticketing agreement; ONDC and BMRCL |
| "Pay for current bus ticket" (wallet, UPI, cards) | None (refusing adapter) | WAITING FOR OFFICIAL API/PERMISSION | BMTC agreement and an RBI-authorised payment aggregator |
| "Buy bus pass" (daily or monthly) | None (refusing adapter) | WAITING FOR OFFICIAL API/PERMISSION | BMTC pass rules and agreement |
| "Buy metro ticket" (QR) | None (refusing adapter) | WAITING FOR OFFICIAL API/PERMISSION | ONDC registration and BMRCL approval |
| Ticket selection by passenger type (Senior citizen, Adult, Child) with fares and a fare split | None | NOT IMPLEMENTED; fares WAITING FOR OFFICIAL API/PERMISSION | Verified fare tables and ticketing rules |
| "My Tickets" | None | NOT IMPLEMENTED (depends on ticketing) | Ticketing agreement |
| Profile (icon on Home) | Accounts built on the server; no screens; switched off | IMPLEMENTED BUT NOT FULLY VERIFIED | A permanent database, then the account screens |
| Distribution: Google Play (1L+ downloads, 4.1 stars from 1.99K reviews, as shown on 19 Nov 2026) | Web app (installable); Android APK and AAB compile in CI; not on Play | IMPLEMENTED BUT NOT FULLY VERIFIED | Device tests; release key; Play account |

## Present in this app (not assessed for the official app)
These are not claims that the official app lacks them; the screenshots simply do not show them.

| Feature | Status here |
|---|---|
| Service notices copied from official sources, with the source linked and an end date | IMPLEMENTED AND TESTED |
| Quick destinations, shareable journey links, swap, start from my location | IMPLEMENTED AND TESTED |
| Every result labelled with its data source; approximate times marked | IMPLEMENTED AND TESTED |
| Upcoming transport register with dated sources | IMPLEMENTED AND TESTED |
| English, Kannada, Telugu and Hindi interface | IMPLEMENTED AND TESTED (native review pending) |
| Offline timetables after the first visit | IMPLEMENTED AND TESTED |
| Emergency numbers on one tap | IMPLEMENTED AND TESTED (web); Android not device-tested |
| Automated accessibility scan (WCAG 2.1 AA) on every screen | IMPLEMENTED AND TESTED |

## Summary
The capabilities that make the official app most useful (live bus positions and arrivals, bus data, tickets, passes,
Metro QR and payments) all depend on BMTC's and BMRCL's own systems. None can be built honestly without their data or
agreements. The rest of the gap is engineering that needs no permission and is listed in
[IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md).
