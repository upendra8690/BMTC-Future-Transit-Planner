# 13 Pilot implementation plan

**A draft for discussion. It has not been approved.** The pilot would start only after written permission to use
official data and the authority's written agreement to the scope below (gates in
[22](22_APPROVALS_AGREEMENTS_AND_CREDENTIALS.md)).

## 1. Purpose
To measure whether the application gives passengers correct, understandable and useful journey information on one
corridor, using only officially provided data, and to give the authority evidence for its own decision.

## 2. Scope
| Item | Proposal |
|---|---|
| Corridor | One corridor chosen by the authority, for example a BMTC feeder route to a Metro station |
| Data | Official GTFS for that corridor only, under a written licence, verified against the publisher before day 1 |
| In scope | Route and stop search, timetables, bus, Metro and combined journeys, saved journeys on the phone, four languages, offline timetables |
| Out of scope | Live tracking, arrival estimates, tickets, passes, QR tickets, payments, NCMC, notifications; passenger accounts unless the authority asks for them |
| Platforms | The web app (any phone browser, installable). The Android app only if it has passed tests on at least two phones |
| Participants | 30 to 50 adult volunteers, recruited openly; at least three screen-reader users; no minors |
| Duration | 8 weeks: 2 weeks preparation, 4 weeks use, 2 weeks analysis and report |
| Privacy | No personal data beyond optional anonymous feedback; "Delete my data" available; all pilot data deleted at the end |
| Naming | "Independent pilot with the permission of [authority]", in wording the authority approves. Never "official app" |

## 3. Timeline and gates
| Week | Activity | Done when | Gate |
|---|---|---|---|
| Before 0 | Written data licence and pilot permission | Documents received | G1, G2 |
| 0–1 | Paid hosting, PostgreSQL with daily backups, uptime monitoring; official feed imported and verified (100 sampled departures) | Verification evidence recorded | — |
| 1–2 | Security fixes from [20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md) closed; audit if the authority requires it; privacy notice reviewed; translations reviewed; screen-reader test | Each item signed off | G3 |
| 2 | Participant briefing (in English and Kannada); feedback form tested | Briefing held | — |
| 3–6 | Live use; weekly status report to the authority's officer | 4 weekly reports | — |
| 7–8 | Analysis; final report with every measure, including failures; data deletion | Report delivered; deletion confirmed | G6 (the authority decides) |

## 4. Roles
| Role | Responsible for |
|---|---|
| Authority's nominated officer | Scope, data, approval of wording, receiving reports, stop decision |
| Applicant (developer) | Hosting, data import and verification, fixes, support, reports, data deletion |
| Participants | Using the app on real trips; optional feedback |
| Independent reviewer (if required) | Security audit; accessibility review |

## 5. Success indicators (measured and reported as found)
| Indicator | How measured | Target |
|---|---|---|
| Timetable accuracy | 100 sampled departures compared with the published schedule | ≥ 98 % match |
| Journey-planning success | Requests where service exists that return a valid journey | ≥ 95 % |
| Availability | Uptime check every 5 minutes | ≥ 99 % |
| Accessibility | Automated WCAG 2.1 AA scan; screen-reader users' feedback | 0 automated violations; every reported issue logged |
| Data integrity | Unverified or demonstration data shown as official | 0; any case stops the pilot |
| Privacy | Personal data collected beyond optional feedback | None |
| Usefulness | Participant rating and comments | Reported as measured; no target set in advance |

## 6. Risks
| Risk | Likelihood | Effect | Response |
|---|---|---|---|
| Official data differs from what runs on the road | Medium | Wrong times shown | Sample checks each week; label "scheduled, not live"; report errors to the publisher |
| Hosting outage | Low with paid hosting | No service | Monitoring; backups; restore drill before day 1 |
| Security issue found | Low–medium | Risk to participants | Fix first; stop the pilot if participants are affected |
| Misunderstanding about official status | Medium | Reputational risk to the authority | Approved wording on every screen; briefing |
| Developer unavailable | Medium (one developer) | Slow fixes | Small scope; documented runbook; weekly status |

## 7. Stopping and exit
- The pilot stops at once if permission is withdrawn, if any data is shown wrongly as official, or if a security issue
  affects participants.
- At the end, pilot data is deleted, and the authority's data is removed if its licence ends with the pilot.
- **Taking part does not imply endorsement**, and the application will not say that it does.
