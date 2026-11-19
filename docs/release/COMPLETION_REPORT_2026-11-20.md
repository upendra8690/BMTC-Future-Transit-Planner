# Completion report: 19–20 November 2026 (branch `v4`)

No approval from BMTC, BMRCL, DULT or the Government of Karnataka exists or is claimed. Each statement below names its
test. The full 105-row matrix is in [FEATURE_MATRIX.md](FEATURE_MATRIX.md), and the integrations are in
[../integrations/INTEGRATION_REGISTER.md](../integrations/INTEGRATION_REGISTER.md).

## Stages and commits
| Stage | Commit | What changed |
|---|---|---|
| Accounts and administrator roles | `b589e30` | Individual administrator accounts; the shared key only assigns roles; account screens |
| Map selection; CSP | `50c8935` | "Choose on map"; `style-src 'self'` (S4 fixed) |
| Live tracking subsystem | `228420a` | GTFS-Realtime adapter, Live screen, stop arrivals (off until a feed is authorised) |
| Tickets and payments model; CI fix | `2549b74` | Orders, payments, tickets, refunds; PostgreSQL CI job fixed |
| UPI payment architecture | `170612e` | Server-side confirmation, Razorpay adapter, sandbox, BMTC ticketing adapter |
| Brand | `3c226db` | The owner's logo for PWA, favicon, splash and Android icons |
| Documents and Android test | this report's commit | Integration register, request draft, feature matrix, emulator results |

CI passed 4 of 4 jobs (Python 3.12 and 3.13, container, PostgreSQL) on `2549b74` and `170612e`, push and pull request.
`228420a` failed the PostgreSQL job; it was fixed in `2549b74`.

## A. What works today
- **On the public service** (https://bengaluru-transit-planner-v4.onrender.com, real mode):
  - Metro journeys with up to two changes, using community data labelled "Unverified feed";
  - choosing the start and destination on the map, swapping them, and starting from my location;
  - shared journey links, favourites, recent searches;
  - service notices from official sources only;
  - four languages, offline shell, emergency numbers, upcoming transport.

  `verify_deployment.py` reports "all checks passed". The strict CSP is live.
- **Built and tested, waiting for the owner's database:** passenger accounts and individual administrator accounts
  with roles (`tests/test_accounts.py` 35, `accounts_check.py` 24/24 on a local server with accounts on).

## B. UPI payments
- **Works now, in the sandbox only:**
  - server-side confirmation by signed webhook or status API;
  - unique transaction ids, duplicate protection and a single attempt per order;
  - expiry, with late payments refunded;
  - refunds, receipts, history and the audit log.

  Tests: 17 sandbox scenarios, 21 adapter tests, 24 workflow tests, browser 15/15. They cover success, failure,
  pending, duplicate callback, invalid signature, time-out, refund and a restart mid-payment.
- **Needs merchant onboarding:** the Razorpay adapter (UPI Intent through payment links, UPI QR codes, refunds and
  webhooks). It is tested against recorded responses only. To verify it, the owner needs a merchant account, test
  keys, a webhook secret and an https address.

## C. Needs BMTC or BMRCL authorisation
| Item | Missing |
|---|---|
| Bus routes, stops and timetables on official data | BMTC GTFS and its licence |
| Live buses and arrival estimates | BMTC GTFS-Realtime feeds, access key and agreement |
| Bus tickets and passes | BMTC ticketing API specification, sandbox, credentials and agreement (`BmtcTicketingAdapter` refuses until then) |
| Metro QR tickets | ONDC registration and BMRCL approval |
| Combined tickets | A joint product from both operators |
| Official fares, Metro data | BMTC and BMRCL fare data; the official BMRCL feed |
| NCMC | Issuing-bank and operator agreements |

## D. Not implemented
- notification delivery;
- complaint handling;
- security alerting;
- Android deep links;
- an iOS app;
- browser and accessibility tests in CI;
- an incident-response procedure;
- an independent security audit.

See the matrix for the decision or provider each one needs.

## E. Android
See the "Android emulator test" section in [ANDROID_EMULATOR_TEST.md](ANDROID_EMULATOR_TEST.md). It was run on an
emulator, not on a physical device.
