# 13 Pilot proposal

**This pilot is a draft for discussion only. It has not been approved.** It would start only after written permission
to use official data and the authority's agreement to the scope below.

## Purpose
To measure whether the application gives passengers correct and useful bus and Metro journey information on one
corridor, using officially provided data.

## Scope
| Item | Proposal |
|---|---|
| Corridor | One bus and Metro corridor chosen with the data owner, for example a feeder route to a Metro station |
| Data | Official GTFS for that corridor only, under a written licence; verified against the publisher before use |
| Features in scope | Route and stop search, timetables, bus, Metro and combined journeys, saved journeys, the four languages |
| Features out of scope | Live tracking, tickets, passes, QR tickets, payments, NCMC, accounts, notifications |
| Participants | 30 to 50 adult volunteers, recruited openly, including at least three screen-reader users; no minors |
| Duration | 6 weeks: 1 week set-up, 4 weeks use, 1 week analysis and report |
| Privacy | Guest mode only; no personal data beyond optional anonymous feedback; "Delete my data" available; all pilot data deleted at the end on request |
| Support | The applicant, by email; problems logged publicly with no personal data |
| Hosting | Paid always-on hosting with PostgreSQL and daily backups (see [14](14_IMPLEMENTATION_AND_MAINTENANCE_COSTS.md)) |

## Prerequisites (all required before day 1)
1. A written data licence and the authority's written agreement to the pilot scope.
2. The official feed imported, then verified by comparing a sample with the publisher's source.
3. Paid hosting, PostgreSQL with backups, and uptime monitoring.
4. The Android app tested on at least two phones, or a pilot run in the web app only.
5. A legal review of the privacy policy; a named contact for complaints.
6. Native-speaker review of Kannada, plus Telugu and Hindi if those are in scope.

## Success indicators (measured and reported as found)
| Indicator | How measured | Target |
|---|---|---|
| Timetable accuracy | 100 sampled departures compared with the published schedule | ≥ 98 % match |
| Journey-planning success | Requests where service exists that return a valid journey | ≥ 95 % |
| Availability | Uptime check every 5 minutes | ≥ 99 % |
| Accessibility | Automated WCAG 2.1 AA scan; feedback from screen-reader users | 0 automated violations; issues reported |
| Data integrity | Any demonstration or unverified data shown as official | 0; any case stops the pilot |
| Privacy | Personal data collected beyond optional feedback | None |
| Usefulness | Participant rating and comments | Reported as measured; no target set in advance |

## Governance and exit
- **Reporting.** A short weekly status report to the authority's nominated officer, and a final report with all
  measures, including failures.
- **Stopping.** The pilot stops at once if permission is withdrawn, if any data is shown wrongly as official, or if a
  security issue affecting participants is found.
- **No implied approval.** Taking part in the pilot does not imply endorsement, and the application will not say that
  it does.
