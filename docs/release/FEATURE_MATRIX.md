# Feature matrix: all 105 tracked requirements (20 November 2026)

Branch `v4`. Built from `REQUIREMENTS_REGISTER.md` (the source, the wording of each requirement and its history), with the
changes verified on 19 and 20 November 2026. **No row is approved by BMTC, BMRCL, DULT or the Government of Karnataka.**
Statuses:

| Status | Count | Share |
|---|---|---|
| Implemented and tested | 40 | 38 % |
| Implemented but not fully verified | 23 | 22 % |
| Demonstration only | 10 | 10 % |
| Awaiting official integration | 23 | 22 % |
| Not implemented | 9 | 9 % |

What these numbers mean:
- **Implemented and tested:** it works on the public service or, where noted, on a local server, with the test named.
- **Implemented but not fully verified:** the code exists and its tests pass, but it has not run where it will be used,
  such as the public service (accounts need a permanent database), a phone, or a real provider.
- **Demonstration only:** it works only with invented data on a demonstration server, labelled on every screen.
- **Awaiting official integration:** it cannot reach passengers without the API, data, credential or agreement named in
  the last column. Where code exists, it is tested with test data only.
- **Not implemented:** it does not exist yet, usually waiting for an owner decision (named).

The app is **not** complete. Most of what passengers expect from Namma BMTC (live buses, bus data, tickets, passes and
payments) cannot become real without official data and agreements.

| ID | Requirement | Status | What works today, with test evidence | Exactly what is missing |
|---|---|---|---|---|
| A-01 | Registration | **Implemented but not fully verified** | Register screen with one-time recovery code. `tests/test_accounts.py` (35); `tests/browser/accounts_check.py` 24/24 (local server with accounts on) | Off on the public service until the owner configures a permanent PostgreSQL database (`DATABASE_URL`, `ACCOUNTS_ENABLED=1`) |
| A-02 | Sign-in and sign-out | **Implemented but not fully verified** | Sign-in and sign-out screens; staff sessions 12 h, page memory only. `tests/test_accounts.py` (35); `tests/browser/accounts_check.py` 24/24 (local server with accounts on) | Off on the public service until the owner configures a permanent PostgreSQL database (`DATABASE_URL`, `ACCOUNTS_ENABLED=1`) |
| A-03 | OTP verification | **Awaiting official integration** | None | SMS provider and TRAI DLT registration; a decision that phone numbers may be collected |
| A-04 | Profile and preferences | **Implemented but not fully verified** | Account screen: role, saved journeys, notification choices; device settings. `tests/test_accounts.py` (35); `tests/browser/accounts_check.py` 24/24 (local server with accounts on) | Off on the public service until the owner configures a permanent PostgreSQL database (`DATABASE_URL`, `ACCOUNTS_ENABLED=1`) |
| A-05 | Password recovery | **Implemented but not fully verified** | Recovery with the one-time code (screen and server). `tests/test_accounts.py` (35); `tests/browser/accounts_check.py` 24/24 (local server with accounts on) | Off on the public service until the owner configures a permanent PostgreSQL database (`DATABASE_URL`, `ACCOUNTS_ENABLED=1`); email reset needs an email provider |
| A-06 | Account deletion and data export | **Implemented but not fully verified** | Download my account data; delete account (screens). `tests/test_accounts.py` (35); `tests/browser/accounts_check.py` 24/24 (local server with accounts on) | Off on the public service until the owner configures a permanent PostgreSQL database (`DATABASE_URL`, `ACCOUNTS_ENABLED=1`) |
| A-07 | Privacy settings and notice | **Implemented but not fully verified** | Draft privacy policy; location asked only on tap. Evidence: Document 20, section 5 | Legal review |
| B-01 | Bus route search | **Demonstration only** | Works on invented demonstration data only (`DEMO_MODE=1`, labelled); e2e on a demonstration server | BMTC's official static GTFS (routes, stops, trips, calendar) and its licence, from DULT's Transport Data Hub or BMTC |
| B-02 | Bus stop search | **Demonstration only** | Works on invented demonstration data only (`DEMO_MODE=1`, labelled); e2e on a demonstration server | BMTC's official static GTFS (routes, stops, trips, calendar) and its licence, from DULT's Transport Data Hub or BMTC |
| B-03 | Route numbers and stop lists | **Demonstration only** | Works on invented demonstration data only (`DEMO_MODE=1`, labelled); e2e on a demonstration server | BMTC's official static GTFS (routes, stops, trips, calendar) and its licence, from DULT's Transport Data Hub or BMTC |
| B-04 | Route maps | **Demonstration only** | Works on invented demonstration data only (`DEMO_MODE=1`, labelled); e2e on a demonstration server | BMTC's official static GTFS (routes, stops, trips, calendar) and its licence, from DULT's Transport Data Hub or BMTC |
| B-05 | Stop information and departures | **Demonstration only** | Works on invented demonstration data only (`DEMO_MODE=1`, labelled); e2e on a demonstration server | BMTC's official static GTFS (routes, stops, trips, calendar) and its licence, from DULT's Transport Data Hub or BMTC |
| B-06 | Timetables, first and last trips, CSV | **Demonstration only** | Works on invented demonstration data only (`DEMO_MODE=1`, labelled); e2e on a demonstration server | BMTC's official static GTFS (routes, stops, trips, calendar) and its licence, from DULT's Transport Data Hub or BMTC |
| B-07 | Service status of a route on a date | **Demonstration only** | Works on invented demonstration data only (`DEMO_MODE=1`, labelled); e2e on a demonstration server | BMTC's official static GTFS (routes, stops, trips, calendar) and its licence, from DULT's Transport Data Hub or BMTC |
| B-08 | Bus service categories (for example Vajra, Vayu Vajra) | **Awaiting official integration** | Not shown | Category data from BMTC |
| B-09 | Depot information | **Awaiting official integration** | None | BMTC data and permission |
| B-10 | Airport bus information | **Demonstration only** | Works on invented demonstration data only (`DEMO_MODE=1`, labelled); e2e on a demonstration server | BMTC's official static GTFS (routes, stops, trips, calendar) and its licence, from DULT's Transport Data Hub or BMTC |
| C-01 | Live bus location | **Awaiting official integration** | Live subsystem built: `tests/test_realtime.py` (26), `tests/browser/live_check.py` 15/15 with a labelled test feed | BMTC GTFS-Realtime VehiclePositions and TripUpdates feeds (https URLs, access key) matching the official static GTFS, under a data-sharing agreement |
| C-02 | Vehicle tracking on a map | **Awaiting official integration** | Live subsystem built: `tests/test_realtime.py` (26), `tests/browser/live_check.py` 15/15 with a labelled test feed; live map with vehicle markers | BMTC GTFS-Realtime VehiclePositions and TripUpdates feeds (https URLs, access key) matching the official static GTFS, under a data-sharing agreement |
| C-03 | Estimated arrival times | **Awaiting official integration** | Live subsystem built: `tests/test_realtime.py` (26), `tests/browser/live_check.py` 15/15 with a labelled test feed; estimates per stop ahead, delay propagation, scheduled times labelled | BMTC GTFS-Realtime VehiclePositions and TripUpdates feeds (https URLs, access key) matching the official static GTFS, under a data-sharing agreement |
| C-04 | Stop-wise arrivals | **Awaiting official integration** | Live subsystem built: `tests/test_realtime.py` (26), `tests/browser/live_check.py` 15/15 with a labelled test feed; live arrivals on stop pages, labelled | BMTC GTFS-Realtime VehiclePositions and TripUpdates feeds (https URLs, access key) matching the official static GTFS, under a data-sharing agreement |
| C-05 | Service disruption alerts | **Awaiting official integration** | Administrator-posted notices from official sources work (E-03); no automatic alerts feed | BMTC and BMRCL service alerts (GTFS-Realtime Alerts or an official alerts API) |
| C-06 | Real-time refresh | **Awaiting official integration** | Live subsystem built: `tests/test_realtime.py` (26), `tests/browser/live_check.py` 15/15 with a labelled test feed; 20 s refresh, poll limit | BMTC GTFS-Realtime VehiclePositions and TripUpdates feeds (https URLs, access key) matching the official static GTFS, under a data-sharing agreement |
| C-07 | GPS freshness indicator | **Awaiting official integration** | Live subsystem built: `tests/test_realtime.py` (26), `tests/browser/live_check.py` 15/15 with a labelled test feed; Live/Delayed per vehicle, feed age, positions older than 10 min hidden | BMTC GTFS-Realtime VehiclePositions and TripUpdates feeds (https URLs, access key) matching the official static GTFS, under a data-sharing agreement |
| D-01 | Origin and destination with stop search | **Implemented and tested** | Stop search, use my location, and choose on map: `tests/browser/map_and_policy_check.py` 13/13; phase 2 18/18 | — |
| D-02 | Bus-only journeys | **Demonstration only** | Works on invented demonstration data only (`DEMO_MODE=1`, labelled); e2e on a demonstration server | BMTC's official static GTFS (routes, stops, trips, calendar) and its licence, from DULT's Transport Data Hub or BMTC |
| D-03 | Metro-only journeys | **Implemented and tested** | Planner `modes=metro`. Evidence: Public check: Indiranagar to Jayanagar | Official BMRCL GTFS for "Officially verified"; today community data, labelled |
| D-04 | Combined bus and Metro journeys | **Demonstration only** | Works on invented demonstration data only (`DEMO_MODE=1`, labelled); e2e on a demonstration server | BMTC's official static GTFS (routes, stops, trips, calendar) and its licence, from DULT's Transport Data Hub or BMTC |
| D-05 | Walking connections | **Implemented and tested** | Walking transfers between nearby stops. Evidence: e2e (demonstration data); pytest | — |
| D-06 | Transfers (up to two changes) | **Implemented and tested** | Round-based search. Evidence: Public check: changes at Majestic and RV Road | — |
| D-07 | Journey alternatives, labelled | **Implemented and tested** | Options ranked; "Earliest arrival", "Fewest changes". Evidence: pytest | — |
| D-08 | Accessible (step-free) journey options | **Awaiting official integration** | None | Station and stop accessibility data |
| D-09 | Travel-time information | **Implemented and tested** | Duration per option and ride; Metro times approximate. Evidence: pytest; public check | — |
| D-10 | Leave now or choose a date and time | **Implemented and tested** | Plan screen. Evidence: e2e | — |
| D-11 | Correct wording per mode | **Implemented and tested** | The wait names the mode of the first ride (Metro train, bus, other). Evidence: Browser check: no "first bus" on a Metro journey (18 Nov 2026) | — |
| D-12 | Swap start and destination | **Implemented and tested** | Swap button. Evidence: `phase2_check.py` | — |
| D-13 | Start from my location (nearest stop or station) | **Implemented and tested** | Nearest stop or station, never an entrance. Evidence: `phase2_check.py`; regression test | Location permission |
| D-14 | Share a journey and open a shared journey | **Implemented and tested** | Journey links; Web Share, clipboard or on-page link. Evidence: `phase2_check.py` | — |
| E-01 | Digital bus tickets, passes, renewal | **Awaiting official integration** | Order, payment, ticket and refund model with provider interfaces; sandbox for demonstration servers. `tests/test_commerce.py` (24), `tests/test_payment_sandbox.py` (17), `tests/test_razorpay_adapter.py` (21), `tests/browser/payments_sandbox_check.py` 15/15 | BMTC ticketing API specification, sandbox and credentials, and a ticketing agreement; `BmtcTicketingAdapter` refuses until then |
| E-02 | Ticket validation, QR codes, receipts, refunds, history | **Awaiting official integration** | Receipts and refunds work in the sandbox; tickets are stored exactly as a provider issues them; the app never draws a ticket QR. `tests/test_commerce.py` (24), `tests/test_payment_sandbox.py` (17), `tests/test_razorpay_adapter.py` (21), `tests/browser/payments_sandbox_check.py` 15/15 | BMTC's ticket and pass QR format, its validation by conductors or gates, and cancellation rules |
| E-03 | Service announcements by administrators (with official source links and end dates) | **Implemented and tested** | Service notices on Home; admin editor; official-source allow-list; 31-day limit; audit log. Evidence: `tests/test_notices.py`; `phase2_check.py` | — |
| F-01 | Approved payment gateway, UPI | **Implemented but not fully verified** | Razorpay adapter: UPI payment links (intent and QR), UPI QR codes; merchant settings checked at start-up. `tests/test_commerce.py` (24), `tests/test_payment_sandbox.py` (17), `tests/test_razorpay_adapter.py` (21), `tests/browser/payments_sandbox_check.py` 15/15 | Owner's merchant onboarding with an RBI-authorised payment aggregator; test keys to verify the adapter; live keys for production |
| F-02 | Verification, webhooks, idempotency | **Implemented and tested** | Signed webhooks (HMAC-SHA256), server-side status checks, each event once, idempotent orders, one attempt at a time, unique transaction ids. `tests/test_commerce.py` (24), `tests/test_payment_sandbox.py` (17), `tests/test_razorpay_adapter.py` (21), `tests/browser/payments_sandbox_check.py` 15/15 | Run once against the provider's test mode after merchant onboarding |
| F-03 | Refunds and reconciliation | **Implemented and tested** | Refunds, automatic refund of late or unissued payments, `POST /api/admin/payments/reconcile`. `tests/test_commerce.py` (24), `tests/test_payment_sandbox.py` (17), `tests/test_razorpay_adapter.py` (21), `tests/browser/payments_sandbox_check.py` 15/15 | Run once against the provider's test mode after merchant onboarding |
| F-04 | Fraud prevention | **Awaiting official integration** | Exact-amount check, signature check, single attempt, no payment secrets accepted. `tests/test_commerce.py` (24), `tests/test_payment_sandbox.py` (17), `tests/test_razorpay_adapter.py` (21), `tests/browser/payments_sandbox_check.py` 15/15 | The payment aggregator's risk and fraud tools after onboarding |
| F-05 | NCMC | **Awaiting official integration** | Refusing adapter. Evidence: pytest | Issuing bank and operator |
| G-01 | Favourite stops | **Implemented and tested** | Device list. Evidence: e2e | — |
| G-02 | Saved journeys | **Implemented and tested** | Device list; plan again. Evidence: e2e | — |
| G-03 | Saved routes on the server | **Implemented but not fully verified** | Works; on free hosting saved routes are lost on restart and the app says so | Permanent database (L-07) |
| G-04 | Recent searches | **Implemented but not fully verified** | Device list. Evidence: Code review | — |
| G-05 | Notifications | **Not implemented** | Preferences stored per account (`tests/test_accounts.py`); nothing is sent | Owner decision on the channel (web push, email or SMS) and its keys or provider |
| G-06 | Language: English, Kannada, Telugu, Hindi | **Implemented and tested** | 629 texts in each. Evidence: pytest (key parity); launch check 268/268 | Native-speaker review |
| G-07 | Customer support and help | **Not implemented** | Official websites and helplines listed. Evidence: e2e links | A decision by the owner or the government: Which official channel to use |
| G-08 | Complaints and feedback | **Not implemented** | None in the app | A decision by the owner or the government: BMTC decides whether complaints go to its own channel |
| G-09 | Emergency information and dialler | **Implemented and tested** | 112, 108, 101, 1098 as phone links (web). Evidence: e2e (web) | Android: fixed in code, not device-tested |
| G-10 | Offline use | **Implemented and tested** | Service worker: shell and saved timetables. Evidence: e2e offline steps | — |
| G-11 | Upcoming transport with status labels | **Implemented and tested** | Register with sources and history. Evidence: pytest 17; browser 17 | — |
| G-12 | Rule-based travel assistant | **Implemented and tested** | Fixed rules, app data only. Evidence: pytest | — |
| G-13 | Feature list states only what is true | **Implemented and tested** | Fares reported only when shown; temporary server storage reported. Evidence: pytest (`tests/test_client_ip_and_labels.py`) | — |
| G-14 | Quick destinations | **Implemented and tested** | Major Metro stations present in the data, labelled. Evidence: `phase2_check.py` | — |
| H-01 | Stations (Purple, Green, Yellow) | **Implemented and tested** | 83 stations, community data, labelled. Evidence: Public check | Official BMRCL data for "Officially verified" |
| H-02 | Line information | **Implemented and tested** | Lines and stop lists. Evidence: Real-mode check | Same |
| H-03 | Interchanges | **Implemented and tested** | Majestic, RV Road. Evidence: Public check | — |
| H-04 | Metro schedules | **Implemented and tested** | Approximate times, labelled. Evidence: Public check | Official timetables |
| H-05 | Pink Line | **Awaiting official integration** | Upcoming transport only | No timetable in any source; owner decision on a station list |
| H-06 | Metro fares | **Awaiting official integration** | Withheld (estimates only in source). Evidence: pytest | Official fares and permission |
| H-07 | Metro ticketing | **Awaiting official integration** | Refusing adapter; official link. Evidence: pytest | ONDC registration and BMRCL approval |
| I-01 | GTFS import with validation and limits | **Implemented and tested** | Administration and command line. Evidence: pytest | — |
| I-02 | Verification workflow (only OFFICIAL can be verified) | **Implemented and tested** | Yes. Evidence: pytest; e2e | — |
| I-03 | Feed freshness status | **Implemented and tested** | `/api/data-status`. Evidence: Public deployment check | — |
| I-04 | Scheduled synchronisation from an official source | **Awaiting official integration** | None | An official source to synchronise from |
| I-05 | GTFS-Realtime ingestion with freshness checks | **Implemented but not fully verified** | Live subsystem built: `tests/test_realtime.py` (26), `tests/browser/live_check.py` 15/15 with a labelled test feed | BMTC GTFS-Realtime VehiclePositions and TripUpdates feeds (https URLs, access key) matching the official static GTFS, under a data-sharing agreement |
| I-06 | Documented adapter per provider capability | **Implemented and tested** | Yes, all refusing. Evidence: pytest | — |
| J-01 | Administrator sign-in | **Implemented but not fully verified** | Individual administrator accounts; the shared key only assigns roles while accounts run. `tests/test_accounts.py` (35); `tests/browser/accounts_check.py` 24/24 (local server with accounts on) | Off on the public service until the owner configures a permanent PostgreSQL database (`DATABASE_URL`, `ACCOUNTS_ENABLED=1`); until then the shared key is used |
| J-02 | Role-based access (passenger, editor, admin) | **Implemented but not fully verified** | passenger, editor and admin; editors see only notices and upcoming transport. `tests/test_accounts.py` (35); `tests/browser/accounts_check.py` 24/24 (local server with accounts on) | Off on the public service until the owner configures a permanent PostgreSQL database (`DATABASE_URL`, `ACCOUNTS_ENABLED=1`) |
| J-03 | User management | **Implemented but not fully verified** | Accounts and roles panel; last administrator protected; `scripts/create_admin.py`. `tests/test_accounts.py` (35); `tests/browser/accounts_check.py` 24/24 (local server with accounts on) | Off on the public service until the owner configures a permanent PostgreSQL database (`DATABASE_URL`, `ACCOUNTS_ENABLED=1`) |
| J-04 | Route and stop management | **Implemented and tested** | Through GTFS import, not hand editing. Evidence: pytest | The data owner manages its own data |
| J-05 | Data and API health monitoring | **Implemented but not fully verified** | Health and data-status endpoints; no alerting. Evidence: Public check | Monitoring service (free tier) |
| J-06 | Audit log of sensitive actions | **Implemented and tested** | Yes. Evidence: pytest | — |
| J-07 | Operational reports | **Implemented but not fully verified** | Basic statistics. Evidence: pytest | Requirements from the authority |
| J-08 | Ticket monitoring, payment reconciliation | **Awaiting official integration** | Payment reconciliation endpoint and audited payment events. `tests/test_commerce.py` (24), `tests/test_payment_sandbox.py` (17), `tests/test_razorpay_adapter.py` (21), `tests/browser/payments_sandbox_check.py` 15/15 | Connected ticketing and payment providers |
| J-09 | Complaint management | **Not implemented** | None | A decision by the owner or the government: G-08 |
| J-10 | Security alerts | **Not implemented** | None | Monitoring service |
| K-01 | Responsive web at 390 px and desktop | **Implemented and tested** | Yes. Evidence: Launch check 268/268 | — |
| K-02 | Responsive web at 320, 360, 375, 412, 430 px, tablet and desktop | **Implemented and tested** | Yes. Evidence: `tests/browser/responsive_check.py` 22/22 (11 screens at 10 widths) | — |
| K-03 | Installable PWA with offline shell | **Implemented but not fully verified** | Manifest, icons, service worker. Evidence: e2e (Edge) | Device install not tested |
| K-04 | Firefox and Safari | **Implemented but not fully verified** | Standard web code | Not tested |
| K-05 | Android debug APK | **Implemented but not fully verified** | CI compiles the APK (target API 36). Build script `scripts/android/build_test_apk.ps1` and emulator check `tests/android/emulator_check.py` are committed. A local build on 20 Nov was blocked (pub.dev connections refused, errno 10013), so the app has not run on an emulator or device (`docs/release/ANDROID_EMULATOR_TEST.md`) | An APK to test: allow dart.exe network access on the build computer, or set `V4_PLANNER_URL` and run the workflow manually (publishes a pre-release; needs the owner's approval) |
| K-06 | Android signed release APK and AAB | **Implemented but not fully verified** | CI builds an AAB and signs with the owner's key when the four GitHub secrets exist | The owner's upload key in GitHub secrets |
| K-07 | Android location for "near me" | **Implemented but not fully verified** | Asked only when the page asks; never retained. Evidence: CI compile and analyze (`d72e5c9`) | Not run on a device |
| K-08 | Android load-error retry and downloads | **Implemented but not fully verified** | Try again; downloads to the share sheet. Evidence: CI compile and analyze (`d72e5c9`) | Not run on a device |
| K-09 | Android deep links | **Not implemented** | None | Domain verification file |
| K-10 | iPhone and iPad (Safari PWA) | **Implemented but not fully verified** | Standard web code; bottom safe area only | Not tested on a device |
| K-11 | iOS app project and signing | **Awaiting official integration** | None | A Mac or a macOS CI runner; Apple Developer Program |
| L-01 | OWASP self-assessment with a findings register | **Implemented and tested** | Document 20. Evidence: 18 Nov 2026 | — |
| L-02 | Reliable per-visitor rate limiting | **Implemented and tested** | Counted by the hosting edge's visitor address (R1 fixed). Evidence: Live test 18 Nov 2026; pytest | — |
| L-03 | CSP without inline styles | **Implemented and tested** | `style-src 'self'`, no inline styles; static and header tests; 20 screens with no refusal (`map_and_policy_check.py` 13/13); live site checked | — |
| L-04 | Secrets only in the hosting environment | **Implemented and tested** | Yes. Evidence: Commit scan | — |
| L-05 | Dependency and static scans in CI on every push | **Implemented and tested** | bandit and pip-audit in the CI test jobs. Evidence: CI `5ef03ed` | — |
| L-06 | Browser and accessibility tests in CI | **Not implemented** | Run by hand only | — |
| L-07 | Permanent database with backups | **Implemented but not fully verified** | PostgreSQL proven in CI (migrations, restart persistence, accounts); backup script | The owner's PostgreSQL database (Neon free tier or Render) |
| L-08 | Incident response procedure | **Not implemented** | None | — |
| L-09 | Logging policy that satisfies CERT-In without recording searches or locations | **Not implemented** | No access log | A decision by the owner or the government: Authority's decision |
| L-10 | Independent security audit | **Awaiting official integration** | None | Auditor; authority's requirement |
| L-11 | Screen-reader and native-language review | **Awaiting official integration** | Automated scans only. Evidence: axe 0 violations | Volunteers or reviewers |
