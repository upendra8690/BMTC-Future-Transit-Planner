# Known limitations — 4.0.0-beta.1

1. **All timetable data is invented demo data.** No BMTC or BMRCL data is loaded, because no licence has been
   obtained. Every journey, route, stop and fare in the demo is fictional ("Demo Central", "Demo Metro Hub", ...).
2. **No live data.** There are no bus positions, ETAs, delays, cancellations or alerts. Every time is a scheduled time.
3. **No tickets, passes, Metro QR, payments, wallet or NCMC transactions.** The app links to official channels.
4. **No user accounts.** Data is tied to a device key. Clearing the browser loses it, and on free hosting it is lost
   on every restart.
5. **Travel assistant:** rules only, English questions only. It recognises journeys ("A to B", "by bus", "by metro"),
   route numbers, stop names, Metro stations, "near me", and live, ticket and emergency questions. Anything else gets
   help text.
6. **Upcoming transport** is status information from press and secondary sources, checked on 17 November 2026. It
   can go out of date, and the planner never uses it.
7. **Facilities** (hospitals, toilets, parking, EV charging, and so on) are not listed, because no licensed dataset is
   loaded. Emergency numbers and official links are listed.
8. **Translations** have not been professionally reviewed. Server-supplied descriptions (upcoming projects, provider
   details) are in English.
9. **Maps** need internet access to OpenStreetMap tiles, under their light-use policy.
10. **Android:** the 4.0 APK has not been built or tested on a device.
11. **Hosting:** free Render instances sleep when idle, so the first request after a pause can take about a minute.
    The region is Singapore, so data is processed outside India; this needs review under the DPDP Act.
12. **Open security findings:** S4 (inline styles allowed by the CSP) and S5 (shared admin key). No independent
    penetration test has been done.
13. **Performance** was measured on a laptop with demo data (20 concurrent users, 0 errors, p95 ≤ 150 ms). It is not
    representative of citywide data.
