> **DRAFT. NOT SENT.** This letter goes on top of each submission. Fill in the bracketed fields and use the addressee
> from the matching request (15 BMTC, 16 BMRCL, 17 DULT).

[Date]

To
[Designation of the officer]
[Organisation and office address, from document 19]

**Subject: Submission of an independent Bengaluru journey planner for technical review**

Respected Sir/Madam,

I am an independent developer from Bengaluru. I submit Bengaluru Transit Planner, version 4.0, for your technical
review. It is a free web application, with an Android wrapper in preparation, that plans public-transport journeys in
English, Kannada, Telugu and Hindi.

I wish to state clearly:
- **It is unofficial.** It is not approved by, endorsed by or affiliated with BMTC, BMRCL, DULT or the Government of
  Karnataka, and it uses no government logo.
- **No official data is used.**
  - The public preview shows real Namma Metro journeys from an unofficial community reconstruction of BMRCL's
    published timetables. They are labelled "Unverified feed", with approximate times and no fares.
  - It has no BMTC bus data.
  - Invented demonstration data runs only on a separate demonstration server.
- **No tickets, payments or live information.** Each stays switched off until written authorisation exists.
- **No personal data.** It collects no names, phone numbers, email addresses, locations or payment details.

The enclosed package documents the application with evidence, including its open findings and limitations:
- 512 automated tests pass on the current code (18 November 2026);
- all 869 on-screen controls were exercised in a browser;
- the automated accessibility scan (WCAG 2.1 AA) found no violations;
- the security self-assessment lists its open findings. None is rated high severity. There has been no independent
  penetration test.

**I respectfully request:**
1. technical feedback on the application;
2. guidance on the official source and licence for bus and Metro schedule data;
3. permission to use authorised data under your terms;
4. a short meeting with your technical team, with a demonstration;
5. consideration, at a later stage and subject to your approval, of a small, time-limited pilot.

I am not requesting endorsement, funding or procurement.

Thank you for your time and consideration.

Yours faithfully,

[Signature]
Mopuru Upendra Reddy
Independent developer, Bengaluru
[Email address] · [Mobile number]

Enclosures: as listed in document 19, section C.
Source code and evidence: https://github.com/upendra8690/BMTC-Future-Transit-Planner-3.0 (branch `v4`, folder
`government_submission_2026/`)
Public preview: https://bengaluru-transit-planner-v4.onrender.com (check it with scripts/verify_deployment.py on the day of sending)
