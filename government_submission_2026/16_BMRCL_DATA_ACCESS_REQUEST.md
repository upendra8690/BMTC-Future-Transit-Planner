> **DRAFT. NOT SENT.** Before sending:
> - Fill in the bracketed fields.
> - Ask which officer handles data-sharing requests. The BMRCL contact page (checked 18 Nov 2026) lists the project
>   office telephone as 080-2296 9300 and 080-2296 9301, the Chief Public Relations Officer as 080-22969300, and the
>   Director (Projects and Planning) as 080-22969206.
> - Use the project-related office below, not the passenger travel-help channel (travelhelp@bmrc.co.in).

[Date]

To
The Managing Director
Bangalore Metro Rail Corporation Limited
3rd Floor, BMTC Complex, K.H. Road, Shanthinagar
Bengaluru 560027

Kind attention: [the officer responsible for passenger information systems or open data, to be confirmed by
telephone]

**Subject: Request for official Namma Metro station, timetable and fare data, and guidance on integration, for an
independent passenger journey planner**

Respected Sir/Madam,

Bengaluru Transit Planner is a free web application, with an Android wrapper in preparation, that plans Namma Metro
journeys in English, Kannada, Telugu and Hindi. **It is unofficial and is not affiliated with, endorsed by or
authorised by BMRCL.** It sells no tickets, draws no QR codes and takes no payments.

**I wish to be transparent about the Metro data it shows today.** The public preview (address below) shows the
Purple, Green and Yellow lines from **bmrcl-gtfs**. This is an independent community reconstruction of BMRCL's
published timetables, released under the Open Database Licence (ODbL).
- It is labelled "Unverified feed" on every journey, with "approximate times".
- Its fares are never shown, because they are estimates.
- The elevated Pink Line is missing, because it opened after the community file was last updated.
- **If BMRCL prefers that this community data not be shown, I will remove it promptly on request.** My aim is to
  replace it with BMRCL's own data under BMRCL's terms.

**I respectfully request:**
1. **Official station, line and timetable data**, including the Pink Line, in GTFS format if available, with the
   licence or terms for use in a free public application. If it is published through the DULT Transport Data Hub, its
   current address and terms.
2. **Fare data**, and permission to show it, if BMRCL allows.
3. **Station information** if it can be shared: exits, lifts, escalators and accessible entrances.
4. **Answers to the questions in the annex**, or a short meeting with the relevant officer, with a 20-minute
   demonstration.
5. **For information only:** the approved route for a third-party application to offer Metro QR tickets. I understand
   it involves ONDC registration and BMRCL's approval. The application will not offer tickets without them.

**My commitments:**
- BMRCL data will be shown with its source and date.
- It will be labelled "Officially verified" only after it has been checked against BMRCL's published source.
- It will never be altered, will be used only under BMRCL's terms, and will be removed on request.
- The application will not describe itself as official, approved or a BMRCL partner.

Enclosures: 01 Executive summary; 04 Feature matrix; 09 Data and licence register; 12 Demonstration guide; the annex
below.

Yours faithfully,

[Signature]
Mopuru Upendra Reddy
Independent developer, Bengaluru
[Email address] · [Mobile number]
Source code: https://github.com/upendra8690/BMTC-Future-Transit-Planner-3.0 (branch `v4`)
Public preview: https://bengaluru-transit-planner-v4.onrender.com (check it with scripts/verify_deployment.py on the day of sending)

---

## Annex: Metro data and questions for BMRCL
**Data the application can use**

| Data | Detail | Used for |
|---|---|---|
| Stations | Names in English and Kannada, coordinates, line, interchange stations | Station search, maps |
| Timetables | Departures at every station (not only terminals), first and last trains, weekday, Sunday and holiday patterns | Journey planning without approximate times |
| Pink Line | Stations and timetable of the open section | Journeys to the new stations |
| Fares | Fare table between stations, and any rules on showing it | Fares, only if permitted |
| Station facilities | Exits, lifts, escalators, accessible entrances, parking | Accessibility information |
| Service updates | Planned closures, changed timings | Notices with an official source |

**Questions**
1. Is BMRCL's GTFS published today, and where? Press reports from 2024 name the DULT Transport Data Hub, but its address
   did not resolve on 18 November 2026.
2. What licence or terms apply, and what attribution wording does BMRCL require?
3. Until official data is available, does BMRCL object to the community reconstruction being shown with the labels
   described above?
4. May timetables be stored on passengers' phones for offline use?
5. How are timetable changes and new sections announced, and how quickly is the data updated?
6. May fares be shown, and from which source?
7. How may the application refer to Namma Metro and BMRCL, and what disclaimer wording is required?
8. Does BMRCL publish any real-time train information or service alerts for third parties?
9. Which officer should the applicant contact for data questions?
