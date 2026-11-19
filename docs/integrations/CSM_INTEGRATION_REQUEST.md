# Draft: technical integration request to BMTC's Chief Systems Manager

**Status: draft, not sent.** Before sending, the owner should:
- confirm the officer's current name, designation and address on BMTC's official website (the designation "Chief
  Systems Manager" comes from the owner's brief and has not been checked);
- fill in the bracketed fields;
- attach the documents listed at the end.

---

To
The Chief Systems Manager
Bangalore Metropolitan Transport Corporation (BMTC)
Central Offices, K.H. Road, Shanthinagar, Bengaluru

From
[Owner's full name], developer of Bengaluru Transit Planner (an independent project)
[Address] · [Phone] · [Email]

Date: [date]

**Subject: Request for technical access to BMTC data and APIs for evaluation of Bengaluru Transit Planner 4.0**

Sir/Madam,

I have built Bengaluru Transit Planner, an independent web and Android app for journeys in Bengaluru. It is **not** an
official BMTC app. It does not use BMTC's name or logo as its own, and it says so on every screen. I request technical
access so that BMTC can evaluate it, and, if BMTC so decides, consider a limited pilot. I do not ask for any approval
in this letter, and the app claims none.

**1. What is built and tested today (source code and test results available for review)**
- **Journey planning:** bus, Metro and combined journeys with up to two changes and walking transfers, choosing places
  on a map or from the device's location, and four languages (English, Kannada, Telugu, Hindi).
- **Timetable data:** a GTFS importer with validation, source verification and clear labels. Data is shown as
  "official" only after an administrator verifies an official source.
- **Live tracking:** a GTFS-Realtime adapter (vehicle positions and trip updates) for a live map, next stop, route
  progress, arrival estimates and stop-wise arrivals. It is switched off: without BMTC's feed the app shows "Not
  connected" and never invents positions or predictions.
- **Tickets and payments:** an order, payment, ticket and refund system that confirms payments only through the payment
  provider's signed notifications or status API, and never issues a ticket by itself. It is tested only in a sandbox
  labelled "DEMONSTRATION ONLY — NOT VALID FOR TRAVEL". No ticket is sold today.
- **Security:**
  - individual administrator accounts with roles and an audit log;
  - a strict content security policy and rate limiting;
  - secrets only in the hosting environment;
  - no card, UPI PIN or OTP ever collected.

**2. What I request (any subset is useful)**
| # | Item | Purpose |
|---|---|---|
| 1 | BMTC static GTFS (routes, stops, trips, timetables, calendars, shapes) and the licence terms for public display | Bus search, timetables and journeys on official data |
| 2 | GTFS-Realtime VehiclePositions and TripUpdates (test endpoint first) with an access key | Live map and arrival estimates, clearly labelled |
| 3 | Service alerts (GTFS-Realtime Alerts or an equivalent feed) | Disruption notices |
| 4 | Fare tables and the rules for showing them | Correct fares in journey results |
| 5 | Ticketing and pass API documentation and a sandbox: fare quotes, issue, ticket and QR format, validation, cancellation and refunds | To build and test BMTC ticketing in BMTC's sandbox before any live use |
| 6 | Contact for a security review and the conditions for a pilot | To meet BMTC's security and data-protection requirements |

**3. Commitments**
- Data will be used only to inform passengers. It will be labelled with its source and freshness, and never altered or
  presented as BMTC's own app.
- No ticket, pass or QR code will be issued, and no payment taken, without BMTC's written authorisation and a
  separately agreed merchant arrangement.
- Credentials will be kept only in the hosting environment, never in source code. Access can be revoked by BMTC at any
  time.
- Personal data will follow the DPDP Act, 2023. The app collects no personal data except what passengers choose to
  store in an optional account.
- Security findings will be fixed before any pilot, and BMTC or its auditors may test the system.

**4. Proposed next steps**
1. A technical meeting to agree data formats and access.
2. Test access to rows 1 and 2.
3. A demonstration to BMTC on BMTC's data.
4. If BMTC wishes, a written pilot scope with acceptance criteria.

I would be grateful for an appointment at your convenience.

Yours faithfully,
[Owner's full name]

**Enclosures (to attach):**
- integration register (`docs/integrations/INTEGRATION_REGISTER.md`);
- feature matrix (`docs/release/FEATURE_MATRIX.md`);
- security audit (`docs/audit/SECURITY_AUDIT.md`);
- live tracking design (`docs/integrations/LIVE_TRACKING.md`);
- payments design (`docs/integrations/PAYMENTS_AND_TICKETING.md`);
- a link to the public demonstration service.
