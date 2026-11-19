# Pilot proposal (draft — not approved)

**Purpose.** Measure whether the app gives commuters correct, useful bus and Metro journey information on one corridor,
using officially provided data.

| Item | Proposal |
|---|---|
| Corridor | One bus–Metro corridor chosen with the data owner (example: a feeder route to a Purple Line station) |
| Data | Official GTFS for that corridor only, under a written licence |
| Participants | 30–50 adult volunteers (no minors), recruited openly; no personal data collected beyond optional feedback |
| Duration | 6 weeks: 1 week set-up, 4 weeks use, 1 week analysis |
| Support | Developer by email; issues logged publicly on GitHub (no personal data) |
| Privacy | Guest mode only; "Delete my data" available; no location stored |

## Success criteria (measured, reported honestly)
| Measure | Target |
|---|---|
| Timetable accuracy (sampled departures vs published schedule) | ≥ 98 % match |
| Journey-planning success (requests that return a valid option where service exists) | ≥ 95 % |
| Service availability (uptime check every 5 minutes) | ≥ 99 % on paid always-on hosting |
| Accessibility | No WCAG 2.1 AA violations in automated scans; at least 3 participants using screen readers |
| Participant usefulness rating | Reported as measured; no target claimed in advance |

## Risks and exit conditions
Stop the pilot immediately if the data owner withdraws permission, if any data is shown wrongly as official, or if a
security issue affecting participants is found. Data is removed at the end on request.

## Costs (estimate, to confirm)
Always-on hosting and a persistent database for 6 weeks: a few thousand rupees in total; volunteer time; no cost to
the authority beyond providing data and feedback.
