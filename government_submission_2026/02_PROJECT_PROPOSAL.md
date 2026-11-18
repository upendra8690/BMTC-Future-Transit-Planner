# 02 Project proposal

**Applicant:** Mopuru Upendra Reddy, independent developer, Bengaluru.
**Status:** an independent, unofficial application. **Nothing here is an approved or official government project.**
The addressed versions of this proposal are the requests to BMTC ([15](15_BMTC_DATA_ACCESS_REQUEST.md)), BMRCL
([16](16_BMRCL_DATA_ACCESS_REQUEST.md)) and DULT ([17](17_DULT_TECHNICAL_REVIEW_REQUEST.md)).

## 1. The problem
A passenger who combines a BMTC bus with Namma Metro has to piece the journey together from separate sources.
- Information is mostly in English.
- It is hard to tell what runs today from what is only planned.

Details are in [03](03_PROBLEM_AND_PUBLIC_BENEFIT.md).

## 2. What the application offers
- One journey across bus, Metro and walking, from scheduled timetables, with up to two changes.
- A choice of bus only, Metro only, or both.
- English, Kannada, Telugu and Hindi, with large text, dark mode and a low-data mode.
- The source and reliability of every piece of information: officially verified, or unverified.
- Emergency numbers (112, 108, 101, 1098) and links to each operator's official website.
- A status for each upcoming transport project, with sources. A planned service is never shown as running.

## 3. Where it stands (18 November 2026)
| Area | Position |
|---|---|
| Namma Metro | Real Purple, Green and Yellow line journeys from an unofficial community reconstruction of BMRCL's published timetables (ODbL). Labelled "Unverified feed", approximate times, no fares. Pink Line missing |
| BMTC buses | **No real data.** Bus planning is built and tested on invented demonstration data only, which runs on a separate demonstration server |
| Live tracking, tickets, passes, payments | Not available; each stays off until written authorisation exists |
| Quality | 501 automated tests pass; browser, accessibility and security checks recorded in [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md) |
| Open findings | Listed openly in [20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md); none rated high severity |
| Requirements | 101 requirements tracked; 27 % implemented and verified; 44 % need permission, a provider or a decision (`docs/release/REQUIREMENTS_REGISTER.md`) |

## 4. What official data would change
With a data licence and the official GTFS files:
- bus route, stop and timetable search in four languages;
- bus journeys and combined bus and Metro journeys;
- Metro times without approximation, and the Pink Line;
- fares, where the operator permits.

The import, validation and verification path already exists, so no code changes are needed for this ([05](05_SYSTEM_ARCHITECTURE.md),
section 6).

## 5. Support requested from the authorities
1. Technical review and feedback.
2. The official source and licence for BMTC and BMRCL GTFS. Press reports from 2024 describe a DULT Transport Data Hub.
3. Permission, in writing, to use that data in a free public application.
4. A meeting with the relevant technical team, with a 20-minute demonstration ([21](21_PRESENTATION_OUTLINE.md)).
5. Later, consideration of a limited pilot, subject to approval ([13](13_PILOT_PROPOSAL.md)).

**Not requested:** endorsement, funding, procurement, branding rights or any blanket approval.

## 6. Security, privacy and accessibility
- **No personal data in use.** No accounts are in use; a random device key is stored only as a hash; no location or
  search history is stored; there is no analytics.
- **Security.** A self-assessment against OWASP, with open findings listed and fixes planned. No independent test yet
  ([06](06_TECHNICAL_AND_SECURITY_REPORT.md), [20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md)).
- **Data protection.** Designed for the DPDP Act, 2023 and Rules, 2025; legal review before any pilot
  ([07](07_PRIVACY_AND_DATA_PROTECTION.md)).
- **Accessibility.** No automated WCAG 2.1 AA violations on 15 screens in two themes. Screen-reader and native-language
  reviews are pending ([08](08_ACCESSIBILITY_AND_LANGUAGE_SUPPORT.md)).

## 7. Commitments
- Official data is labelled official only after verification against the publisher's own source.
- Data is never altered, is used only under the publisher's terms, and is removed on request.
- No logos, and no claim of approval, partnership or endorsement.
- No imitation of live tracking, tickets, QR codes or payments.
- Every number shown to the authority comes from a recorded test run with its date.

## 8. Costs
₹0 today. A minimum pilot costs about US$13 a month, borne by the applicant. Assurance items such as a security audit
are quoted separately ([14](14_IMPLEMENTATION_AND_MAINTENANCE_COSTS.md)).

## 9. Next steps and gates
| Gate | Event | Follows |
|---|---|---|
| G1 | Written data route and licence | Official data imported and verified |
| G2 | Written pilot permission and hosting decision | Pilot preparation |
| G3 | Security and privacy sign-off, if required | Pilot start (8 weeks) |
| G4 onwards | Real-time, ticketing and payment agreements | Separate projects, only if the authority wishes |

Details are in [22](22_APPROVALS_AGREEMENTS_AND_CREDENTIALS.md).
