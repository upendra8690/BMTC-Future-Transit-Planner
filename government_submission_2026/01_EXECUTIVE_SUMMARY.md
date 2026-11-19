# 01 Executive summary

**Bengaluru Transit Planner, version 4.0.0-beta.1. Submitted for technical review, November 2026.**

This is an independent and unofficial project. BMTC, BMRCL, DULT and the Government of Karnataka have not approved,
endorsed, authorised or partnered with it. It sells no tickets, takes no payments and shows no live vehicle positions.

## What it is
Bengaluru Transit Planner is a free, mobile-first web application. An Android wrapper is being prepared. It helps a
passenger:
- plan journeys across Namma Metro, buses and walking;
- see scheduled times;
- tell running services from planned ones.

It works in **English, Kannada, Telugu and Hindi**. Pages already visited remain readable without a connection. It
collects no names, phone numbers, email addresses or payment details.

## Where it stands today (18 November 2026)
| Area | Position |
|---|---|
| Transport data | **No official data.** The public preview shows real Namma Metro Purple, Green and Yellow line journeys from an *unofficial community reconstruction* of BMRCL's published timetables (ODbL licence). It is labelled "Unverified feed" with "Approximate times", and its fares are never shown. **There is no real BMTC bus data.** Invented demonstration data appears only on a separate demonstration server |
| Software quality | 512 automated tests pass on the current code. In browser tests, all 869 on-screen controls worked. The automated accessibility scan (WCAG 2.1 AA) found no violations. See [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md) |
| Security | Self-assessment, not an independent test. Open findings are listed, none of high severity. A rate-limit weakness (R1) found on 18 Nov 2026 was fixed and verified on the public service the same day. See [20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md) |
| Live tracking, tickets, passes, Metro QR, payments, NCMC | **Not available.** Each needs written authorisation; until then the app says it is unavailable and points to the official channel |
| Public availability | https://bengaluru-transit-planner-v4.onrender.com, in real mode; every deployment check passed on 18 Nov 2026 |
| Android | A WebView wrapper that compiles in CI. Not yet tested on a phone; no release-signed build |
| Authorisation | None. See [22](22_APPROVALS_AGREEMENTS_AND_CREDENTIALS.md) |

## What we request
1. A **technical review** of the application and its documentation.
2. **Guidance on official data sources**: where BMTC and BMRCL schedule data (GTFS) is published, and its licence.
3. **Permission to use authorised data** under written terms, starting with static schedules.
4. A **discussion with the relevant technical team**, including a 20-minute demonstration.
5. **Consideration of a limited, time-bound pilot** on one corridor, only after the steps above and only if approved.
   See [13](13_PILOT_PROPOSAL.md).

We are **not** asking for endorsement, funding, procurement or any form of blanket approval.

## Package contents
| Deliverable | Documents |
|---|---|
| A. Government-ready project proposal | [02 Project proposal](02_PROJECT_PROPOSAL.md), [03 Problem and public benefit](03_PROBLEM_AND_PUBLIC_BENEFIT.md), [04 Feature matrix](04_COMPLETE_FEATURE_MATRIX.md) |
| B. Technical architecture | [05 Technical architecture](05_SYSTEM_ARCHITECTURE.md) |
| C. Data permission requests | [15 BMTC: proposal and data request, with data requirements and technical questions](15_BMTC_DATA_ACCESS_REQUEST.md); [16 BMRCL: Metro data and integration request](16_BMRCL_DATA_ACCESS_REQUEST.md); [17 DULT: technical coordination proposal](17_DULT_TECHNICAL_REVIEW_REQUEST.md); [09 Data and licence register](09_DATA_SOURCE_AND_LICENCE_REGISTER.md) |
| D. Cybersecurity and privacy checklist | [20 Security, privacy, accessibility, reliability, data governance](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md); [06 Security report](06_TECHNICAL_AND_SECURITY_REPORT.md); [07 Privacy](07_PRIVACY_AND_DATA_PROTECTION.md); [08 Accessibility](08_ACCESSIBILITY_AND_LANGUAGE_SUPPORT.md) |
| E. Pilot implementation plan | [13 Pilot implementation plan](13_PILOT_PROPOSAL.md); [14 Budget, including a zero-budget option](14_IMPLEMENTATION_AND_MAINTENANCE_COSTS.md) |
| F. Presentation outline | [21 Presentation outline](21_PRESENTATION_OUTLINE.md); [12 Demonstration checklist and script](12_DEMONSTRATION_GUIDE.md) |
| G. Official submission checklist | [19 Submission checklist, verified contacts and channels](19_SUBMISSION_CHECKLIST.md); [22 Approvals, agreements and credentials](22_APPROVALS_AGREEMENTS_AND_CREDENTIALS.md); [18 Cover letter](18_FORMAL_COVER_LETTER.md) |
| Evidence | [10 Test and performance evidence](10_TEST_AND_PERFORMANCE_EVIDENCE.md); [11 Known limitations](11_KNOWN_LIMITATIONS_AND_DEPENDENCIES.md) |

Source code: https://github.com/upendra8690/BMTC-Future-Transit-Planner-3.0 (branch `v4`). The code is public, but no
open-source licence has been chosen yet; see [11](11_KNOWN_LIMITATIONS_AND_DEPENDENCIES.md).
