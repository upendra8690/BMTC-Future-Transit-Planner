# 12 Demonstration checklist and script

About 10 minutes of demonstration inside a 20-minute meeting (slides: [21](21_PRESENTATION_OUTLINE.md)). It uses the
**public address in real mode**, which shows no invented data. An optional appendix uses a separate demonstration
server to show bus planning on invented data.

## Checklist before the meeting
| # | Check | Done |
|---|---|---|
| 1 | Run `scripts/verify_deployment.py` on the day; all checks pass; print the result | ☐ |
| 2 | Open https://bengaluru-transit-planner-v4.onrender.com on the phone and the laptop 5 minutes early (a sleeping server can take up to a minute to wake) | ☐ |
| 3 | In Plan, choose **"Unverified feed"**. The default, "Officially verified", is correctly empty | ☐ |
| 4 | Phone charged; screen brightness up; notifications silenced | ☐ |
| 5 | If administration is shown, sign in before the meeting. **Never show the admin key on screen** | ☐ |
| 6 | If defect D1 is not yet fixed, be ready to say that Metro rides still read "first bus" and that this is being corrected | ☐ |
| 7 | Printed copies: 01, 04, 09, 12, 20 and the matching request with its annex | ☐ |

## Steps (public address)
| # | Show | Do | Say |
|---|---|---|---|
| 1 | Home | Point out the "unofficial" line and the language menu | "Independent and unofficial. No logos, no tickets, no payments." |
| 2 | A real Metro journey | Plan **Majestic** to **Indiranagar** | "A Purple Line journey from a community reconstruction of BMRCL's published timetable. Times are approximate and labelled so; no fare is shown." |
| 3 | A journey with a change | Plan **Indiranagar** to **Jayanagar** | "A change at Majestic, from Purple to Green." |
| 4 | Three lines | Plan **Whitefield** to **Electronic City** | "Purple, Green and Yellow, with changes at Majestic and RV Road." |
| 5 | What is missing | Open the feature list or "Data and providers" | "No bus data, because there is no authorised source. The Pink Line is missing from the community file." |
| 6 | Upcoming transport | Open one entry and its update history | "Each project has a status and dated sources. A planned service is never shown as running." |
| 7 | Languages | Switch to ಕನ್ನಡ, then తెలుగు and हिन्दी, then back | "Every text exists in four languages; a native-speaker review is still needed." |
| 8 | Accessibility | Large text and dark mode | "No automated WCAG 2.1 AA violations; screen-reader testing is next." |
| 9 | Unavailable features | Open Live tracking, then Tickets | "Unavailable until an authorised feed or agreement exists. Nothing is imitated; links go to the official channels." |
| 10 | Offline | Airplane mode on, reopen the app | "The app and timetables already opened still work, marked as saved copies." |

## Appendix: bus planning on a demonstration server (optional)
Run `DEMO_MODE=1 sh scripts/container_start.sh` on the laptop and open http://127.0.0.1:8000/. Every screen then shows
the demonstration banner, and every invented place is named "Demo …".

| Show | Do |
|---|---|
| Bus journey | **Demo Central** to **Demo Junction**, Bus only |
| Bus + Metro journey | **Demo Lake View** to **Demo Metro Hub**, Bus and Metro |
| Verification refused | Administration: try to verify the demo source; it is refused, because only OFFICIAL sources can be verified |

## Questions to expect
| Question | Answer |
|---|---|
| Is any of this official data? | No. The Metro timetable is an unofficial community reconstruction, labelled as such. Official data would be loaded only under your licence and verified against your source. |
| Why show unofficial Metro data at all? | It is real, openly licensed and clearly labelled. If BMRCL objects, it will be removed promptly. |
| Can it show live buses? | Not without an authorised feed. The screens are ready; the feature stays off until then. |
| Does it sell tickets or take payments? | No, and it will not without written agreements. It never stores card or UPI details. |
| Where is passenger data stored? | Only a hashed device key and the items a person saves. No names, phone numbers, searches or locations. |
| Is it secure? | A self-assessment with open findings listed in document 20. There has been no independent penetration test, and we welcome one. |
| What happens if permission is withdrawn? | The data is removed, and the app says the information is unavailable. |
