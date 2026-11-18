# 22 Approvals, agreements and credentials

Checked on 18 November 2026. **No government authority has approved, authorised or commissioned this application.**
No approval letter, agreement, work order, memorandum of understanding, API credential or written technical
instruction from BMTC, BMRCL, DULT or the Government of Karnataka exists in the project or was supplied by the
applicant. Nothing has been sent to any of them yet.

## 1. Authorisation status
| Item an authorised project would need | Evidence found | Status |
|---|---|---|
| Authorising department, officer, reference number and date | None | **Not authorised** |
| Approved project scope and permitted development activities | None | Not authorised |
| Permission to use BMTC or BMRCL data (static timetables, fares) | None | Not authorised. Requested in 15, 16 and 17 |
| Real-time data access (vehicle positions, arrival predictions, alerts) and API credentials | None | Not authorised |
| Use of names, logos or branding of BMTC, BMRCL, Namma Metro or the Government | None | **Not permitted.** The app uses no logo and calls itself unofficial |
| Hosting, security, testing or acceptance requirements | None | Unknown. Questions in the annexes of 15, 16 and 17 |
| Pilot or deployment permission | None | Not authorised. Draft pilot plan in 13 |
| Ticketing, passes, payments, NCMC | None | Not authorised. Features stay switched off |
| Reporting obligations | None | Unknown |
| Verbal or relayed instructions | Not documents | **Not accepted as authorisation.** Any such instruction must be confirmed in writing by the authority that would grant it |

Until a written authorisation exists, the project remains an **independent, unofficial prototype**. Every feature
that depends on permission stays off, and the application says so.

## 2. Approvals and agreements that must be obtained
| # | Approval or agreement | Issued by | Needed for | Prerequisite | Status |
|---|---|---|---|---|---|
| 1 | Data access route and licence for BMTC static schedules (GTFS) | DULT (Transport Data Hub) or BMTC | Real bus routes, stops, timetables | Request 17 or 15 | Not requested yet |
| 2 | Data access route and licence for BMRCL schedules (GTFS), including the Pink Line | DULT or BMRCL | Official Metro timetables replacing the community reconstruction | Request 17 or 16 | Not requested yet |
| 3 | Permission to show fares, with the fare tables | BMTC; BMRCL | Fares | 1 and 2 | Not requested yet |
| 4 | Real-time data-sharing agreement (GTFS-Realtime: vehicle positions, trip updates, alerts) with credentials, rate limits and terms | BMTC (and BMRCL, if it publishes real-time data) | Live tracking, arrival estimates, service alerts | 1; security review; possibly a non-disclosure agreement | Not requested yet |
| 5 | Written pilot permission stating scope, corridor, duration, data handling, reporting and naming rules | BMTC and/or DULT | Any pilot | 1 to 3; 13 | Not requested yet |
| 6 | Security clearance ("safe to host") from NIC, STQC or a CERT-In-empanelled auditor | Auditor, at the authority's request | Hosting for, or on behalf of, a government body (GIGW 3.0, guideline 5.3.1) | A fixed release; paid audit | Not started |
| 7 | Hosting decision: location (India), provider (for example a MeitY-empanelled cloud) and log retention | The authority | A pilot holding authority data or user data | 5 | Not started |
| 8 | Privacy: notice and policy reviewed against the DPDP Act, 2023 and DPDP Rules, 2025; named grievance contact; data-processing terms if the authority is the data fiduciary | Applicant, with legal review; the authority | Any pilot that collects personal data | 5 | Draft policy only (`docs/government/PRIVACY_POLICY.md`) |
| 9 | Ticketing and pass agreement | BMTC | Bus tickets and passes | 5; payment aggregator | Out of scope |
| 10 | ONDC network registration (buyer application) and BMRCL onboarding | ONDC; BMRCL | Metro QR tickets | 5; legal entity | Out of scope |
| 11 | Merchant agreement with an RBI-authorised payment aggregator | Payment aggregator | Any payment | 9 or 10 | Out of scope |
| 12 | NCMC card services | Issuing bank and operator | Card top-up and balance | 11 | Out of scope |
| 13 | Commercial SMS registration on the TRAI DLT platform (entity, sender header, templates) | Telecom operator's DLT portal | SMS notifications, if chosen | A notification decision | Out of scope |
| 14 | Google Play developer account (identity verification) | Google | Play Store distribution | A release-signed app | Not started |
| 15 | Apple Developer Program membership | Apple | iPhone App Store or TestFlight | A Mac build environment | Not started |
| 16 | Code licence decision | Applicant | Describing the code as open source | — | Not decided; say "publicly available" |

## 3. Technical credentials
Credentials are created and held by the stated owner. **None is ever written into the source code, a document, a
chat or a GitHub issue.**

| Credential | Holder | Where it is kept |
|---|---|---|
| Administrator key (`ADMIN_API_KEY`) | Applicant | Generated by the hosting provider; hosting environment only |
| Database address (`DATABASE_URL`) | Applicant | Hosting environment only |
| Official data API keys (if issued) | Applicant, under the issuer's terms | Hosting environment; rotated as the issuer requires |
| Android upload or signing key | Applicant | Offline backup, plus GitHub encrypted secrets for automated builds |
| Apple signing certificates | Applicant | Apple developer account and the build machine's keychain |
| Payment or ticketing keys | Not applicable until 9 to 11 exist | A secrets manager, never the repository |

## 4. Approval gates
Work that needs permission does not start before its gate is passed with a written document.

| Gate | Passed when | Work allowed after it |
|---|---|---|
| G0 (today) | — | Unofficial prototype; public preview in real mode; documentation; work that needs no permission (see `docs/release/PHASE1_BASELINE_AND_ROADMAP.md`) |
| G1 | Written reply naming the official data route and licence (1, 2) | Import official schedules as OFFICIAL; verify them against the publisher; label them "Officially verified" |
| G2 | Written pilot permission (5) and hosting decision (7) | Paid hosting, PostgreSQL with backups, accounts if in scope, pilot preparation |
| G3 | Security clearance (6) and privacy review (8), if the authority requires them | Pilot start |
| G4 | Real-time agreement (4) | Live tracking, arrival estimates and alerts, as a separate change |
| G5 | Ticketing, ONDC and payment agreements (9 to 12) | Ticketing and payment work, under the provider's rules |
| G6 | The authority's written acceptance of the pilot report | Any decision on scale or production. Not assumed |

## 5. Questions for the authorities
The questions that must be answered before any authorised work are in the annexes of the requests:
[15](15_BMTC_DATA_ACCESS_REQUEST.md) (BMTC), [16](16_BMRCL_DATA_ACCESS_REQUEST.md) (BMRCL) and
[17](17_DULT_TECHNICAL_REVIEW_REQUEST.md) (DULT).
