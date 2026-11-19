> **DRAFT. NOT SENT.** Before sending:
> - Fill in the bracketed fields.
> - Confirm the officer and the office by telephone. The officers list is published at
>   mybmtc.karnataka.gov.in/37/officers-list/en. On 18 Nov 2026 that page failed an automated certificate check, so
>   open it in a normal browser to confirm the details.
> - Do not send this to the BMTC complaints address or the control room. Those are passenger channels.

[Date]

To
The Managing Director
Bengaluru Metropolitan Transport Corporation
Central Offices, K.H. Road, Shanthinagar
Bengaluru 560027

Kind attention: [the officer responsible for Information Technology or Intelligent Transport Systems, to be confirmed
by telephone]

**Subject: Project proposal and request for BMTC schedule data (GTFS) and its terms of use, for an independent
multilingual passenger journey planner**

Respected Sir/Madam,

I have developed Bengaluru Transit Planner, a free web application, with an Android wrapper in preparation, that plans
public-transport journeys in English, Kannada, Telugu and Hindi. I submit it for your technical review and request
guidance on the use of BMTC's schedule data.

**The application is unofficial.** It is not affiliated with, endorsed by or authorised by BMTC. It uses no BMTC logo,
sells no tickets, takes no payments and shows no live bus positions or arrival times.

**What it does today.** The public preview (address below) shows real Namma Metro journeys from an unofficial
community reconstruction of BMRCL's published timetables, labelled "Unverified feed" with approximate times. **It has
no BMTC bus data**, because I have found no authorised source and I will not use data copied from BMTC's own app.
Bus planning has been built and tested only on invented demonstration data, which runs on a separate demonstration
server and is labelled on every screen.

**What BMTC data would make possible for passengers:** bus route and stop search in four languages; scheduled
departures; bus journeys with up to two changes; combined bus, Metro and walking journeys; offline timetables on the
phone; and clear "scheduled, not live" labels.

**I respectfully request:**
1. **Static schedule data**: routes, stops, trips, timetables, and fares if they may be shown, in GTFS format, with
   the licence or terms for use in a free public application. If the data is published through the DULT Transport
   Data Hub, its current address and terms.
2. **Information on real-time data**: whether, and under what agreement, BMTC shares vehicle positions, trip updates
   and service alerts with third-party applications. Live features stay switched off until such an agreement exists.
3. **Answers to the technical questions in Annex B**, or a meeting with the officer who can answer them, with a
   20-minute demonstration.
4. **Later, and only if BMTC agrees,** consideration of a small, time-limited pilot on one corridor (document 13).

**My commitments:**
- BMTC data will be shown with its source and date, and labelled "Officially verified" only after it has been checked
  against BMTC's published source.
- It will not be altered or misrepresented, will be used only under BMTC's terms, and will be removed on request.
- The application will not describe itself as official, approved or a BMTC partner.
- It collects no names, phone numbers, locations or payment details.

I am not requesting endorsement, funding or procurement.

Enclosures: 01 Executive summary; 04 Feature matrix; 09 Data and licence register; 12 Demonstration guide;
20 Security and privacy checklist; Annexes A and B below.

Yours faithfully,

[Signature]
Mopuru Upendra Reddy
Independent developer, Bengaluru
[Email address] · [Mobile number]
Source code: https://github.com/upendra8690/BMTC-Future-Transit-Planner-3.0 (branch `v4`)
Public preview: https://bengaluru-transit-planner-v4.onrender.com (check it with scripts/verify_deployment.py on the day of sending)

---

## Annex A: BMTC data the application can use
| Data | Standard | Detail requested | Used for |
|---|---|---|---|
| Agency | GTFS `agency.txt` | Name, time zone, website, public helpline | Attribution and help links |
| Routes | `routes.txt` | Route numbers as shown on buses; service category (for example ordinary, Vajra, Vayu Vajra, Metro feeder) | Route search; airport services |
| Stops | `stops.txt`, `translations.txt` | Stop names in English and Kannada; coordinates; wheelchair access where known | Stop search, maps, nearby stops |
| Trips and times | `trips.txt`, `stop_times.txt` | Which stop times are timed points and which are estimated | Timetables, journey planning |
| Service days | `calendar.txt`, `calendar_dates.txt` | Weekday patterns, holidays, exceptions | Correct service on each date |
| Route paths | `shapes.txt` | Path of each route | Route maps |
| Headway services | `frequencies.txt` | Where buses run by frequency, not fixed times | Honest "every N minutes" display |
| Fares | GTFS fares (v1 or v2) | Stage fares; which concessions may be shown | Fares, only if BMTC permits |
| Feed details | `feed_info.txt` | Version, validity dates, publisher contact | Freshness checks |
| Real time (only under an agreement) | GTFS-Realtime | Vehicle positions, trip updates, service alerts; update interval; credentials; rate limits; availability | Live features, kept off until then |

## Annex B: Technical questions for BMTC
**Data and licence**
1. Is BMTC's static GTFS published today, and where? Press reports from 2024 name the DULT Transport Data Hub
   (`tdh.dult-karnataka.com`), but that address did not resolve on 18 November 2026.
2. Under what licence or terms? What attribution wording does BMTC require?
3. May timetables be stored on passengers' phones for offline use?
4. How often is the feed updated, and how are new routes, diversions and withdrawals announced?
5. Are stop names available in Kannada? Are the stop coordinates surveyed?
6. May fares be shown? If so, which fare products and concessions must be shown, and how?

**Real-time data and alerts**

7. Does BMTC share GTFS-Realtime with third-party applications? Under what agreement, credentials, rate limits and
   service level?
8. What display rules apply to arrival estimates? For example, the required label, and after how many seconds old data
   must be hidden.
9. Is there an official feed of service alerts (diversions, disruptions)?

**Naming, security and hosting**

10. How may the application refer to BMTC, and what disclaimer wording does BMTC require?
11. Does BMTC require a security audit (for example by a CERT-In-empanelled auditor or STQC) before a pilot?
12. Must a pilot be hosted in India, or on a MeitY-empanelled cloud?
13. What logging does BMTC require? The application keeps no access log today, for privacy. CERT-In's 2022
    Directions call for 180 days of logs where they apply.
14. In a pilot, who would be the data fiduciary under the DPDP Act, and what privacy notice is required?

**Pilot and acceptance**

15. Which corridor or routes would BMTC prefer for a pilot, and which officer would be the contact?
16. What acceptance tests would BMTC require: user acceptance, accessibility, languages?
17. What number of users should the service be designed for? The applicant will not assume a target.
18. What reports would BMTC require, and how often?
19. Should passengers be directed to a particular official complaint channel?

**Later (not requested now)**

20. What is the approved route for third-party ticket or pass integration? Press reports describe other applications
    selling BMTC and Metro tickets through ONDC.
