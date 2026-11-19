# Implementation roadmap

Follows the owner's priority order (master instruction, section 12). Status labels are defined in [AUDIT.md](AUDIT.md).
Work that needs official data or an agreement is never faked; it stays clearly unavailable until the document arrives
(gates in `government_submission_2026/22_APPROVALS_AGREEMENTS_AND_CREDENTIALS.md`).

## Phase 1: audit and stability (done)
| Item | Result |
|---|---|
| Repository, security and feature audit | `docs/audit/` (this folder) |
| Rate-limit weakness behind the proxy (R1) | Fixed and verified live |
| Misleading labels (first bus, fares, saved routes, bus claims) | Fixed |
| Nearby stops listing entrances and duplicates | Fixed (19 Nov 2026), regression test |
| CI security scans | bandit and pip-audit on every push |
| Permanent database | Proven in CI; needs the owner's PostgreSQL (decision) |

## Phase 2: core commuter features
| Item | Status |
|---|---|
| Service notices on Home, administered with official sources | IMPLEMENTED AND TESTED |
| Quick destinations (major Metro stations) | IMPLEMENTED AND TESTED |
| Swap, start from my location, shareable journey links | IMPLEMENTED AND TESTED |
| Metro exploration, station directory, Metro journeys | IMPLEMENTED AND TESTED (community data) |
| Bus routes, stops, timetables, combined journeys | Built; DEMONSTRATION ONLY until official bus data |
| Map selection of start or destination | NOT IMPLEMENTED (next) |
| Station accessibility details | WAITING FOR OFFICIAL API/PERMISSION (no data) |

## Phase 3: data integrations
| Item | Status |
|---|---|
| Official GTFS import and verification | IMPLEMENTED AND TESTED (waits only for official files) |
| GTFS-Realtime adapter (vehicle positions, trip updates, alerts) with freshness labels | NOT IMPLEMENTED (next; stays off until a feed is authorised) |
| Live tracking and arrival predictions | WAITING FOR OFFICIAL API/PERMISSION |

## Phase 4: ticketing and payments
| Item | Status |
|---|---|
| Bus tickets, passes, Metro QR, payments, wallet, NCMC | WAITING FOR OFFICIAL API/PERMISSION; refusing adapters in place |
| Sandbox ticket and payment demonstration | NOT IMPLEMENTED: **needs the owner's decision** (below) |

## Phase 5: operations
| Item | Status |
|---|---|
| Admin: imports, verification, backups, audit log, upcoming transport, service notices | IMPLEMENTED AND TESTED |
| Per-person administrator accounts and roles | IMPLEMENTED BUT NOT FULLY VERIFIED (off until PostgreSQL) |
| Monitoring and alerting | NOT IMPLEMENTED (needs a monitoring service) |

## Phase 6: quality and delivery
| Item | Status |
|---|---|
| Automated tests, browser checks, accessibility scans | IMPLEMENTED AND TESTED (see AUDIT.md) |
| Android device testing | Open: needs an emulator build with the public address, or a phone |
| Independent penetration test | Open |

## Decisions needed from the owner
1. **Sandbox tickets and payments.** The master instruction asks for a clearly labelled sandbox. The government package
   (documents 02 and 19) promises the application will not imitate tickets, QR codes or payments. Either keep that
   promise (recommended until an agreement exists), or allow a sandbox on the demonstration server only (never the
   public service), with "NOT A TICKET" on every screen and no QR code, and update documents 02 and 19 before sending.
2. **Simulated vehicles for a live-tracking demonstration.** Same choice: demonstration server only, labelled
   "simulated", or wait for an authorised feed.
3. **Permanent database** (Render PostgreSQL): unlocks accounts, per-person admin roles and durable saved routes.
4. **`V4_PLANNER_URL`** for an Android test build that can run on an emulator or phone.
