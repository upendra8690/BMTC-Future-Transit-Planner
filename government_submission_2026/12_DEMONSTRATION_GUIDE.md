# 12 Demonstration guide and presentation script

The demonstration takes about 15 minutes, followed by questions. It uses only the demonstration data and says so
throughout.

## Before the meeting
- Open the 4.0 staging address on a phone and on a laptop 5 minutes before the meeting. On the free hosting plan a
  sleeping server can take up to a minute to wake.
- **If there is no internet connection or no staging address,** run the app on the laptop:
  `python scripts/migrate_database.py`, then `python scripts/seed_demo_feed.py`, then
  `python -m uvicorn app.main:create_app --factory --app-dir backend --port 8000`, and open
  http://127.0.0.1:8000/. Setup steps are in `docs/INSTALL_WINDOWS.md`. With Docker, instead run
  `docker run -p 8000:8000 -e SEED_DEMO_FEED=1 <image>`.
- For step 12, sign in to Administration before the meeting. **Never show the admin key on screen.**
- In the Plan screen, choose **"Unverified feed"**. The default, "Officially verified", is correctly empty.

## Steps
| # | Show | Do | Say |
|---|---|---|---|
| 1 | Home | Show the search box, map and tiles | "One app for bus and Metro. This is unofficial and runs on invented data today." |
| 2 | Route and stop search | Routes: type `DEMO`; Stops: type `Demo` | "Search by number or name. Every result is labelled with its source." |
| 3 | Bus journey | Plan from **Demo Central** to **Demo Junction**, **Bus only** | "Scheduled times, never live. Each ride shows 'Unverified feed'." |
| 4 | Metro journey | **Demo Metro Central** to **Demo Metro Tech Park**, **Metro only** | "The same planner, Metro only." |
| 5 | Combined journey | **Demo Lake View** to **Demo Metro Hub**, **Bus and Metro** | "A bus ride, a walk to the station and a Metro ride, in one plan." |
| 6 | Saved journey | Tap "Save this journey"; open Favourites; tap "Plan again" | "Saved on the phone itself; no account and no personal data." |
| 7 | Upcoming transport | Scroll | "Each project has a status, sources and a date checked. A planned service is never shown as running." |
| 8 | Languages | Switch to ಕನ್ನಡ, then తెలుగు and हिन्दी, then back | "The whole interface is in four languages; native-speaker review is still pending." |
| 9 | Accessibility | Turn on large text and dark mode | "No automated WCAG 2.1 AA violations; screen-reader testing is the next step." |
| 10 | Data source labels | Open "Data and providers" | "The demo-only banner, and every source with its licence and permission status." |
| 11 | Unavailable live features | Open Live tracking, then Tickets | "Unavailable until an authorised feed or agreement exists. Nothing is imitated; links go to the official channels." |
| 12 | Admin and data status | Administration: the data sources and feeds | "Imports are validated. Only an OFFICIAL source can be verified; here the demo source is refused." |

## Presentation script (about 4 minutes)
> Good morning. Thank you for your time.
>
> I am Mopuru Upendra Reddy, an independent developer in Bengaluru. I have built Bengaluru Transit Planner, a free web
> and Android application that plans journeys combining BMTC buses, Namma Metro and walking, in English, Kannada,
> Telugu and Hindi.
>
> I want to be clear at the start. This is not an official application. It is not approved by or affiliated with BMTC,
> BMRCL, DULT or the Government. Everything you will see today runs on demonstration data that I invented, and the
> application labels it that way on every screen.
>
> *[Steps 1 to 6]* The planner searches bus and Metro timetables together, adds walking transfers, and lets a
> passenger choose bus, Metro or both. Every ride shows where its data came from.
>
> *[Steps 7 to 9]* It shows which new lines and routes are running and which are only planned, with sources. It works
> in four languages, and the automated accessibility checks find no violations.
>
> *[Steps 10 to 12]* Live tracking, tickets and payments are deliberately switched off. The application refuses rather
> than imitate them. A demonstration feed can never be marked as official; only an official source, verified against
> the publisher, can be.
>
> The evidence is in the package: 429 automated tests, a browser test of all 321 controls, security and privacy
> reports, and a list of known limitations.
>
> We are asking for four things. First, your technical feedback. Second, guidance on the official source and licence
> for BMTC and BMRCL schedule data. Third, written permission to use that data. Fourth, a discussion with your
> technical team. If you find it useful, we would also ask you to consider a small, time-limited pilot on one corridor.
> We are not asking for endorsement, funding or procurement.
>
> Thank you. I am happy to answer questions.

## Questions to expect
| Question | Answer |
|---|---|
| Is any of this official data? | No. All of it is invented and labelled. Official data would be loaded only under your licence and verified against your source. |
| Can it show live buses? | Not without an authorised feed. The adapter and screens are ready, and the feature stays off until then. |
| Does it sell tickets or take payments? | No, and it will not without written agreements. It never stores card or UPI details. |
| Where is passenger data stored? | Only a hashed device key and the items a person saves. No names, phone numbers, searches or locations. |
| Who maintains it? | The applicant. The code and test reports are public on GitHub. |
| What happens if permission is withdrawn? | The data is removed and the app returns to demonstration mode. |
