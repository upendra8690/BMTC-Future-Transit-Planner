# 02 Project proposal

**Applicant:** Mopuru Upendra Reddy, independent developer, Bengaluru.
**Status:** an unofficial prototype on demonstration data. Nothing here is an official government project.

## 1. The problem
A passenger in Bengaluru who combines a BMTC bus with Namma Metro has to piece the journey together from separate
sources. Information is mostly in English. Passengers find it hard to tell what is running today from what is only
planned. Details are in [03](03_PROBLEM_AND_PUBLIC_BENEFIT.md).

## 2. How the application helps passengers
- Plans one journey across bus, Metro and walking, from scheduled timetables, with up to two changes.
- Lets the passenger choose bus only, Metro only, or both.
- Works in English, Kannada, Telugu and Hindi, with large text, dark mode and a low-data mode.
- Shows where every piece of information comes from and how reliable it is: official and verified, or unverified.
- Shows emergency numbers (112, 108, 101, 1098) and links to the official websites of each operator.
- Shows a status for each upcoming transport project (operating, under construction, planned), with its sources. It
  never presents a planned service as running.

## 3. BMTC and Metro journey integration
Both operators' schedules are loaded in the international GTFS format. The planner searches across them together and
inserts a walking transfer between a bus stop and a Metro station. Any publisher's GTFS file can be imported, checked
and classified through the administration screen without changing the code. Today only invented demonstration feeds
are loaded. See [05](05_SYSTEM_ARCHITECTURE.md).

## 4. Accessibility and languages
The automated WCAG 2.1 AA scan found no violations on 15 screens, in both light and dark themes. Every screen fits a
390-pixel phone screen without sideways scrolling. Every text in the interface exists in all four languages, and a test
enforces this. The translations have not yet been reviewed by native speakers, and the app has not been tested with a
screen reader. See [08](08_ACCESSIBILITY_AND_LANGUAGE_SUPPORT.md).

## 5. Ready for future transport
- New routes, lines and stations arrive as data, not code. A new GTFS feed is imported and verified.
- Live tracking, tickets, passes, Metro QR, payments and NCMC each have an adapter with a fixed interface. Today each
  adapter refuses every request. A provider can be connected after a written agreement without rewriting the screens.
  See [09](09_DATA_SOURCE_AND_LICENCE_REGISTER.md).

## 6. Data security and privacy
- No accounts. A random key identifies each device, and the server stores only its SHA-256 hash.
- No location or search history is stored, and there is no analytics or access log.
- "Delete my data" removes everything held about a device.
- Administration uses a secret key with constant-time comparison. Inputs are validated, requests are rate limited and
  a strict content security policy applies.

See [06](06_TECHNICAL_AND_SECURITY_REPORT.md) and [07](07_PRIVACY_AND_DATA_PROTECTION.md).

## 7. Architecture
- **Server:** Python FastAPI with SQLAlchemy and Alembic; SQLite for development, PostgreSQL for hosting.
- **App:** a progressive web app written in plain JavaScript, with maps from OpenStreetMap.
- **Packaging:** a Docker container. Testing runs automatically on GitHub Actions.
- **Android:** a Flutter WebView wrapper.

See [05](05_SYSTEM_ARCHITECTURE.md).

## 8. What has been demonstrated
On demonstration data, the following were tested end to end:
- route and stop search, timetables and fares;
- bus, Metro and combined journeys;
- saved journeys;
- the four languages and the offline shell;
- data-source labels and the refusal of every provider action.

The evidence is in [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md).

## 9. Limitations
The main ones:
- no official data;
- no live information;
- no accounts;
- free hosting, which has no persistent database;
- the Android app has not been tested on a phone;
- no independent security test.

The full list is in [11](11_KNOWN_LIMITATIONS_AND_DEPENDENCIES.md).

## 10. Government support requested
1. Technical review and feedback.
2. Guidance on the official source and licence for BMTC and BMRCL GTFS. Press reports from 2024 describe a DULT
   Transport Data Hub.
3. Permission, in writing, to use that data in a free public application.
4. A meeting with the relevant technical team.
5. Consideration of a limited pilot, subject to approval.

## 11. Proposed limited pilot
One corridor, official data for that corridor only, 30 to 50 adult volunteers, six weeks, guest mode only. The pilot
stops at once if permission is withdrawn or any data is shown wrongly as official. See
[13](13_PILOT_PROPOSAL.md).

## 12. Maintenance and sustainability
Today the project costs ₹0 to run: it uses free hosting and has no advertising or data sales. For a pilot it needs
always-on paid hosting and a database with backups, at a modest monthly cost borne by the applicant; see
[14](14_IMPLEMENTATION_AND_MAINTENANCE_COSTS.md).
- **Data:** updates are imported through the administration screen whenever the publisher releases a new feed.
- **Code:** maintained by the applicant, with automated tests on every change.
- **Sustainability:** the application needs no fee from the authority.

## 13. Measurable pilot success indicators
| Indicator | Target |
|---|---|
| Sampled departures match the published schedule | ≥ 98 % |
| Requests where service exists return a valid journey | ≥ 95 % |
| Availability (checked every 5 minutes) | ≥ 99 % |
| Automated WCAG 2.1 AA violations | 0 |
| Data wrongly shown as official | 0 (any case stops the pilot) |
| Personal data collected beyond optional feedback | None |
| Participant usefulness rating | Reported as measured, with no target set in advance |
