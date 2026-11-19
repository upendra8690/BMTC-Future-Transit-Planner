> **DRAFT. NOT SENT.** Before sending:
> - Fill in the bracketed fields.
> - Confirm the addressee's designation by telephone (DULT office, +91-80-22226627). The contact page does not name the
>   head of office.
> - Address, telephone, fax and email below were checked on the official DULT contact page
>   (dult.karnataka.gov.in/67/contact-us/en) on 18 November 2026.

[Date]

To
The Commissioner [confirm designation by telephone]
Directorate of Urban Land Transport
Urban Development Department, Government of Karnataka
BMTC TTMC 'B' Block (above bus stand), 4th Floor
Shantinagar, K.H. Road, Bengaluru 560027
Email: dultbangalore@gmail.com (as published on the DULT contact page)

**Subject: Technical coordination proposal: review of an independent multilingual journey planner, and guidance on
official bus and Metro data (Transport Data Hub)**

Respected Sir/Madam,

I am an independent developer from Bengaluru. I have built Bengaluru Transit Planner, a free web application, with an
Android wrapper in preparation, that plans public-transport journeys in English, Kannada, Telugu and Hindi. **It is
unofficial and is not affiliated with, endorsed by or authorised by DULT, BMTC or BMRCL.** It sells no tickets and shows
no live information.

**Its position today.**
- The public preview (address below) shows real Namma Metro journeys from an unofficial community reconstruction of
  BMRCL's published timetables. They are labelled "Unverified feed", with approximate times and no fares.
- It has no BMTC bus data, because I have found no authorised source.
- Invented demonstration data runs only on a separate demonstration server and is labelled on every screen.

**Why I write to DULT first.** Press reports from 2024 describe BMTC and BMRCL agreeing to publish their schedules
(GTFS) on a DULT Transport Data Hub at `tdh.dult-karnataka.com`. They also describe the agencies agreeing to open
real-time transit data, alongside the Enroute mobility challenge. On 18 November 2026 that address did not resolve,
and I could not find the hub on the DULT website. DULT therefore seems the right office to coordinate the data
question for both operators.

**I respectfully propose and request:**
1. **A technical review** of the application and the enclosed documents, by the officer or team DULT considers
   appropriate.
2. **The current access route to the Transport Data Hub**: its address, any registration process, and the licence or
   terms of use for BMTC and BMRCL data in a free public application.
3. **Coordination of one joint technical meeting** with the BMTC and BMRCL officers concerned, so that data, naming and
   pilot questions are answered once, consistently.
4. **Guidance on the requirements that would apply to a pilot**: security audit, hosting location, accessibility
   (GIGW 3.0) and data protection (DPDP Act, 2023).
5. **Advice on a pilot**: whether a small, time-limited pilot on one corridor could be considered later, subject to
   approval and only after the steps above (draft in document 13).

I am not requesting endorsement, funding or procurement. The application will not describe itself as official,
approved or a partner of any authority.

Enclosures: the complete package, documents 01 to 22; the annex below.

Yours faithfully,

[Signature]
Mopuru Upendra Reddy
Independent developer, Bengaluru
[Email address] · [Mobile number]
Source code: https://github.com/upendra8690/BMTC-Future-Transit-Planner-3.0 (branch `v4`)
Public preview: https://bengaluru-transit-planner-v4.onrender.com (check it with scripts/verify_deployment.py on the day of sending)

---

## Annex: Coordination questions for DULT
1. Is the Transport Data Hub still the official route for BMTC and BMRCL data? What is its current address, and how
   does a developer register?
2. What licence or terms apply to the data, and who signs any data-sharing agreement: DULT or each operator?
3. Is real-time data (vehicle positions, trip updates, alerts) available to independent developers, and on what terms?
4. Which security assurance would DULT expect before a pilot (for example a CERT-In-empanelled audit or STQC
   certification)? Are there hosting-location requirements?
5. Would GIGW 3.0 apply to a pilot run by an independent developer with an authority's permission?
6. Could DULT nominate one officer as the contact for this proposal?
7. Is there a current or planned challenge, sandbox or programme for mobility applications that this proposal should
   use instead?
