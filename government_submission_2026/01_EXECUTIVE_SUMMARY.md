# 01 Executive summary

**Bengaluru Transit Planner, version 4.0.0-beta.1. Submitted for technical review, November 2026.**

This is an independent and unofficial project. BMTC, BMRCL, DULT and the Government of Karnataka have not approved,
endorsed or partnered with it. It sells no tickets, takes no payments and shows no live vehicle positions.

## What it is
Bengaluru Transit Planner is a free, mobile-first web application with a small Android wrapper. It helps a passenger:
- find bus routes and stops;
- see scheduled departures;
- plan journeys that combine BMTC buses, Namma Metro and walking.

It works in **English, Kannada, Telugu and Hindi**. Pages already visited remain readable without a connection. It
collects no names, phone numbers, email addresses or payment details.

## Where it stands today
| Area | Position |
|---|---|
| Transport data | **Demonstration data only.** Two invented feeds, named "Demo …", are labelled as unverified wherever they appear. No official BMTC or BMRCL data is loaded, and no permission has been requested yet. |
| Software quality | **Tested on that demonstration data.** 429 automated tests pass. All 321 buttons, choices and links on 20 screens were exercised in a real browser, and none was decorative or broken. The automated accessibility scan (WCAG 2.1 AA) found no violations. The security self-assessment found no high-severity issue. See [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md). |
| Live tracking, tickets, passes, Metro QR, payments, NCMC | **Not available.** Each needs written authorisation from the operator or provider. Until then the application says it is unavailable and points to the official channel. It never shows an invented result. |
| Public availability | Version 3.0 runs as a public demonstration. Version 4.0 is ready to deploy as a separate staging service; its public address will be supplied with this package. |
| Android | A WebView wrapper around the web application. It has not been tested on a phone yet. |

## What we request
1. A **technical review** of the application and its documentation.
2. **Guidance on official data sources**: where BMTC and BMRCL schedule data (GTFS) is published, and the licence that
   applies.
3. **Permission to use authorised data** under written terms, starting with static schedules.
4. A **discussion with the relevant technical team**, including a 20-minute demonstration.
5. **Consideration of a limited, time-bound pilot** on one corridor, only after the steps above and only if approved.
   See [13](13_PILOT_PROPOSAL.md).

We are **not** asking for endorsement, funding, procurement or any form of blanket approval.

## Package contents
| No. | Document |
|---|---|
| 02 | [Project proposal](02_PROJECT_PROPOSAL.md) |
| 03 | [Problem and public benefit](03_PROBLEM_AND_PUBLIC_BENEFIT.md) |
| 04 | [Complete feature matrix](04_COMPLETE_FEATURE_MATRIX.md) |
| 05 | [System architecture](05_SYSTEM_ARCHITECTURE.md) |
| 06 | [Technical and security report](06_TECHNICAL_AND_SECURITY_REPORT.md) |
| 07 | [Privacy and data protection](07_PRIVACY_AND_DATA_PROTECTION.md) |
| 08 | [Accessibility and language support](08_ACCESSIBILITY_AND_LANGUAGE_SUPPORT.md) |
| 09 | [Data source, licence and integration register](09_DATA_SOURCE_AND_LICENCE_REGISTER.md) |
| 10 | [Test and performance evidence](10_TEST_AND_PERFORMANCE_EVIDENCE.md) |
| 11 | [Known limitations and dependencies](11_KNOWN_LIMITATIONS_AND_DEPENDENCIES.md) |
| 12 | [Demonstration guide and presentation script](12_DEMONSTRATION_GUIDE.md) |
| 13 | [Pilot proposal](13_PILOT_PROPOSAL.md) |
| 14 | [Implementation and maintenance costs](14_IMPLEMENTATION_AND_MAINTENANCE_COSTS.md) |
| 15–17 | Requests to [BMTC](15_BMTC_DATA_ACCESS_REQUEST.md), [BMRCL](16_BMRCL_DATA_ACCESS_REQUEST.md) and [DULT](17_DULT_TECHNICAL_REVIEW_REQUEST.md) |
| 18 | [Formal cover letter](18_FORMAL_COVER_LETTER.md) |
| 19 | [Submission checklist and verified contacts](19_SUBMISSION_CHECKLIST.md) |

Source code: https://github.com/upendra8690/BMTC-Future-Transit-Planner-3.0 (branch `v4`). The code is public, but no
open-source licence has been chosen yet; see [11](11_KNOWN_LIMITATIONS_AND_DEPENDENCIES.md).
