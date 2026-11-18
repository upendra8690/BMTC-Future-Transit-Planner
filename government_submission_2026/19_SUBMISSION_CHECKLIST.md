# 19 Official submission checklist and verified contacts

**Nothing has been sent, and no official has been contacted.** Every item marked "Owner" needs the applicant's own
action or approval.

## A. Before anything is sent
| # | Item | Who | Done |
|---|---|---|---|
| 1 | Run `python scripts/verify_deployment.py https://bengaluru-transit-planner-v4.onrender.com --v3 https://bmtc-future-transit-planner-3-0.onrender.com` on the day. Every line must say PASS. Print the result | Owner | ☐ |
| 2 | Walk through the demonstration ([12](12_DEMONSTRATION_GUIDE.md)) on a phone, on the public address | Owner | ☐ |
| 3 | Decide whether to fix findings R1 and D1 to D4 before sending ([20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md)). Recommended: yes | Owner | ☐ |
| 4 | Decide on a code licence. Until then, say "publicly available", never "open source" | Owner | ☐ |
| 5 | Fill in name, email, mobile number, date and signature in 15, 16, 17 and 18 | Owner | ☐ |
| 6 | Telephone each office to confirm the addressee's designation and the postal address (section B) | Owner | ☐ |
| 7 | Read every page once more. No page may claim approval, partnership, endorsement or official status | Owner | ☐ |
| 8 | Make PDFs or printouts: the cover letter (18), the matching request with its annex (15, 16 or 17), and the enclosures listed in section C | Owner | ☐ |
| 9 | Keep `V4_PLANNER_URL` unset, and publish no 4.0 APK, until the Android app has been tested and you approve | Owner | ☐ |

## B. Contacts checked on the official websites
| Organisation | Use for this submission | Details | Checked | Do not use for this |
|---|---|---|---|---|
| **DULT** | Technical coordination; Transport Data Hub | Directorate of Urban Land Transport, BMTC TTMC 'B' Block (above bus stand), 4th Floor, Shantinagar, K.H. Road, Bengaluru 560027. Phone +91-80-22226627; fax +91-80-22226630; email dultbangalore@gmail.com. The page does not name the head of office | dult.karnataka.gov.in/67/contact-us/en, **18 Nov 2026** | — |
| **BMTC** | Project proposal; GTFS and licence; real-time terms | Central Offices, K.H. Road, Shanthinagar, Bengaluru 560027. Addressee: the Managing Director; officer to be confirmed from the officers list | mybmtc.karnataka.gov.in, 17 Nov 2026. **On 18 Nov 2026 the officers page failed an automated certificate check; confirm it in a browser** | The Control Room and the complaints address are **passenger complaint channels** |
| **BMRCL** | Metro data and licence; integration questions | Project office: Bangalore Metro Rail Corporation Limited, 3rd Floor, BMTC Complex, K.H. Road, Shanthinagar, Bengaluru 560027. Office 080-2296 9300 and 080-2296 9301; Chief Public Relations Officer 080-22969300; Director (Projects and Planning) 080-22969206. No email for official correspondence is published | english.bmrc.co.in/contact/, **18 Nov 2026** | travelhelp@bmrc.co.in and the travel helpline are **passenger channels** |

**Transport Data Hub.** Press reports from 2024 say BMTC and BMRCL schedules are published on a DULT Transport Data
Hub at `tdh.dult-karnataka.com`. On 18 Nov 2026:
- that name did not resolve;
- the DULT website did not mention the hub;
- the only portal it lists is the State Urban Transport Fund portal, which is not a data portal.

Request 17 asks DULT for the current route.

## C. Submission channels: what to send to whom
| To | Channel | Send |
|---|---|---|
| DULT (first) | Registered post with acknowledgement, **and** email to the published address; or delivery by hand at the office's inward section, asking for an inward number | Cover letter 18, request 17, documents 01 to 22 |
| BMTC | Registered post with acknowledgement, or by hand at the Central Offices' inward section | Cover letter 18, request 15 with its annexes, documents 01, 04, 09, 12, 20 (the rest on request) |
| BMRCL | Registered post with acknowledgement, or by hand at the project office | Cover letter 18, request 16 with its annex, documents 01, 04, 09, 12 (the rest on request) |

Keep every postal receipt, acknowledgement card and inward number.

## D. Sending and follow-up (each step needs the owner's approval)
1. Send to DULT first, because DULT may answer the data question for both operators.
2. Send to BMTC and BMRCL in the same week, or after DULT's reply if DULT advises that.
3. Make one polite telephone follow-up 10 working days after delivery, and offer the 20-minute demonstration.
4. Record every dispatch, reply and call in `docs/government/GOVERNMENT_SUBMISSION_STATUS.md`. Record no personal phone
   numbers of officials.
5. If data is granted:
   1. Import it as OFFICIAL with its licence.
   2. Verify it against the publisher's source.
   3. Update document 09.
   4. Only then discuss the pilot (13).

## E. Evidence to have ready for the review
| Evidence | Where |
|---|---|
| Deployment check printed on the day | `scripts/verify_deployment.py` output |
| Automated test results with commit and date | [10](10_TEST_AND_PERFORMANCE_EVIDENCE.md); GitHub Actions page for branch `v4` |
| Security, privacy, accessibility checklist with open findings | [20](20_CYBERSECURITY_AND_PRIVACY_CHECKLIST.md) |
| Data sources, licences and the community-feed audit | [09](09_DATA_SOURCE_AND_LICENCE_REGISTER.md); `docs/launch/DATA_COVERAGE_REPORT.md` |
| Approvals still needed | [22](22_APPROVALS_AGREEMENTS_AND_CREDENTIALS.md) |
| Source code | https://github.com/upendra8690/BMTC-Future-Transit-Planner-3.0 (branch `v4`) |

## F. Never
- Use BMTC, BMRCL, DULT or Government logos, or say "approved", "official", "partner" or "endorsed".
- Contact officials on personal numbers, or through passenger complaint channels, for this proposal.
- Use community feeds copied from the operators' apps, or any private or reverse-engineered interface.
- Show demonstration or unverified data as official, or imitate live tracking, tickets, QR codes or payments.
