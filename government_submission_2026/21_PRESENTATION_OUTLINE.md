# 21 Presentation outline

For a 20-minute meeting with a technical team: about 6 minutes of slides, 10 minutes of live demonstration
([12](12_DEMONSTRATION_GUIDE.md)) and 4 minutes for the requests and questions.

**Rules for every slide:**
- No government, BMTC, BMRCL or Namma Metro logo.
- No words such as "official app", "approved", "partner" or "endorsed".
- Every number on a slide must appear in [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md), with the date it was measured.

| # | Slide title | Key message | Show | Evidence behind it |
|---|---|---|---|---|
| 1 | Bengaluru Transit Planner 4.0: for technical review | An independent, unofficial prototype, submitted for review, not for endorsement | App name, applicant's name, date, the sentence "Independent and unofficial" | — |
| 2 | The passenger problem | Bus and Metro information is spread across separate places, mostly in English, and planned services are easily mistaken for running ones | Three short passenger examples (no invented quotes or statistics) | [03](03_PROBLEM_AND_PUBLIC_BENEFIT.md) |
| 3 | What it does today | Real Namma Metro journeys (Purple, Green, Yellow) from a community reconstruction, with approximate times; four languages; works offline after the first visit | Two phone screenshots: a Metro journey and the Kannada home screen | Public-service check, 18 Nov 2026 |
| 4 | What it does not do | No bus data, live tracking, tickets, passes, payments or accounts. Each stays off until written authorisation exists | The "Unavailable" screen | [04](04_COMPLETE_FEATURE_MATRIX.md), [22](22_APPROVALS_AGREEMENTS_AND_CREDENTIALS.md) |
| 5 | Honest labels | Three classifications: Officially verified, Unverified feed, Estimated scenario. Only official data can ever be verified | Data-sources screen with its labels | [20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md) section 9 |
| 6 | How official data would be loaded | GTFS import, validation, verification against the publisher; no code change needed | Simple flow diagram | [05](05_SYSTEM_ARCHITECTURE.md) |
| 7 | Quality evidence | Automated tests, browser checks, accessibility scans, with dates and commit | Table of results | [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md) |
| 8 | Security and privacy | No personal data collected; self-assessment with open findings listed, not hidden | Open findings table, including R1 | [20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md) |
| 9 | Live demonstration | — | Switch to the phone ([12](12_DEMONSTRATION_GUIDE.md)) | — |
| 10 | Proposed pilot | One corridor, official data only, 30 to 50 adult volunteers, six weeks, stop rules | Timeline with gates G1 to G4 | [13](13_PILOT_PROPOSAL.md) |
| 11 | Cost | ₹0 today; a modest monthly cost for a pilot, borne by the applicant; no funding requested | Budget options table | [14](14_IMPLEMENTATION_AND_MAINTENANCE_COSTS.md) |
| 12 | Our requests | Technical feedback; the official data route and licence; written permission to use the data; a meeting with the technical team; later, consideration of a pilot | Numbered list | [01](01_EXECUTIVE_SUMMARY.md) |
| 13 | Questions to you | The 3 to 5 most important questions from the annex of the matching request | Short list | Annexes of 15, 16, 17 |

## Speaker notes for the opening (slide 1)
> Thank you for your time. I am an independent developer. This application is not official and is not approved by or
> affiliated with your organisation. I am here to ask for your technical review and for guidance on the official data,
> not for endorsement or funding.

## Materials to bring
- A charged Android phone and a laptop, each with the public address already open (it can take up to a minute to wake).
- Printed copies of 01, 04, 09, 12 and the matching request with its annex.
- A printout of the latest results of `scripts/verify_deployment.py`, run on the day.
